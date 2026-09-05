import Foundation

public enum CSVFetcher {
    public static let mirrorPrefixes = [
        "",
        "https://ghfast.top/"
    ]

    public static func getCacheDir() -> URL {
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let dir = appSupport.appendingPathComponent("EQ Cosplay/offline_csvs", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    public static func safeFilename(for name: String) -> String {
        let invalid = CharacterSet(charactersIn: "\\/:*?\"<>| \t\n")
        let parts = name.components(separatedBy: invalid).filter { !$0.isEmpty }
        return parts.joined(separator: "_")
    }

    public static func candidatePaths(for entry: HeadphoneEntry) -> [String] {
        var paths: [String] = []
        let rel = entry.relativePath.replacingOccurrences(of: "\\", with: "/").trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        if rel.isEmpty { return [] }

        func add(_ p: String) {
            let normalized = p.replacingOccurrences(of: "\\", with: "/").trimmingCharacters(in: CharacterSet(charactersIn: "/"))
            if !paths.contains(normalized) {
                paths.append(normalized)
            }
        }

        if rel.lowercased().hasSuffix(".csv") {
            if rel.hasPrefix("results/") || rel.hasPrefix("measurements/") || rel.hasPrefix("offline_csvs/") {
                add(rel)
            } else {
                add("results/\(rel)")
            }
            return paths
        }

        let folder = rel.split(separator: "/").last.map(String.init) ?? ""
        let names = [folder, entry.name].filter { !$0.isEmpty }

        for name in names {
            add("results/\(rel)/\(name).csv")
        }

        let parts = rel.split(separator: "/").map(String.init)
        if parts.count >= 3 {
            let source = parts[0]
            let formRig = parts[1]
            let form = entry.form
            for name in names {
                add("measurements/\(source)/data/\(form)/\(name).csv")
                add("measurements/\(source)/data/\(formRig)/\(name).csv")
                if formRig.contains("711") {
                    add("measurements/\(source)/data/\(form)/711/\(name).csv")
                }
            }
        }

        return paths
    }

    public static func fetchCSV(for entry: HeadphoneEntry) async throws -> (freqs: [Double], mags: [Double]) {
        let safeName = safeFilename(for: "\(entry.name)_\(entry.provider)")
        let cacheFile = getCacheDir().appendingPathComponent("\(safeName).csv")

        // 1. Check local cache
        if FileManager.default.fileExists(atPath: cacheFile.path),
           let cachedData = try? Data(contentsOf: cacheFile),
           let parsed = parseCSVData(cachedData) {
            return parsed
        }

        // Check desktop original project offline_csvs if exists
        let desktopFallback = URL(fileURLWithPath: "/Users/zhuyongfei/Desktop/eq_cosplay/offline_csvs/\(safeName).csv")
        if FileManager.default.fileExists(atPath: desktopFallback.path),
           let data = try? Data(contentsOf: desktopFallback),
           let parsed = parseCSVData(data) {
            try? data.write(to: cacheFile)
            return parsed
        }

        // 2. Download from GitHub / Mirrors
        let candidates = candidatePaths(for: entry)
        var lastError: Error?

        for relPath in candidates {
            let escapedPath = relPath.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? relPath
            let rawUrlString = "https://raw.githubusercontent.com/jaakkopasanen/AutoEq/master/\(escapedPath)"

            for prefix in mirrorPrefixes {
                guard let url = URL(string: "\(prefix)\(rawUrlString)") else { continue }
                var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 12.0)
                request.setValue("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36", forHTTPHeaderField: "User-Agent")

                do {
                    let (data, response) = try await URLSession.shared.data(for: request)
                    if let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode),
                       let parsed = parseCSVData(data) {
                        try? data.write(to: cacheFile)
                        return parsed
                    }
                } catch {
                    lastError = error
                }
            }
        }

        throw lastError ?? NSError(domain: "CSVFetcher", code: -1, userInfo: [NSLocalizedDescriptionKey: "Failed to download CSV for \(entry.name)"])
    }

    public static func parseCSVData(_ data: Data) -> (freqs: [Double], mags: [Double])? {
        guard let text = String(data: data, encoding: .utf8) ?? String(data: data, encoding: .ascii) else {
            return nil
        }

        var freqs: [Double] = []
        var mags: [Double] = []

        let lines = text.components(separatedBy: .newlines)
        for rawLine in lines {
            let line = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
            if line.isEmpty || line.hasPrefix("#") || line.hasPrefix("[") {
                continue
            }

            // Split by comma, tab, semicolon, space
            let parts = line.components(separatedBy: CharacterSet(charactersIn: ",;\t "))
                .map { $0.trimmingCharacters(in: .whitespaces) }
                .filter { !$0.isEmpty }

            guard parts.count >= 2,
                  let f = Double(parts[0]),
                  let m = Double(parts[1]) else {
                continue
            }

            freqs.append(f)
            mags.append(m)
        }

        guard freqs.count >= 3 else { return nil }

        // Sort by frequency ascending
        let paired = zip(freqs, mags).sorted { $0.0 < $1.0 }
        return (paired.map { $0.0 }, paired.map { $0.1 })
    }
}
