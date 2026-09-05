import Foundation

public enum CSVFetcher {
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

    public static func providerCandidates(for entry: HeadphoneEntry) -> [HeadphoneEntry] {
        var ordered: [HeadphoneEntry] = [entry]
        var seenPaths = Set<String>([entry.relativePath])

        let key = entry.name.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let directMatches = AutoEqService.shared.database[key] ?? AutoEqService.builtinFallbackEntries[key] ?? []

        var pool = directMatches
        if pool.isEmpty {
            for (dbKey, list) in AutoEqService.shared.database {
                if dbKey == key || dbKey.contains(key) || key.contains(dbKey) {
                    pool.append(contentsOf: list)
                }
            }
        }

        // Sort others by provider measurement quality / reliability:
        // oratory1990 (GRAS 43AG) > rtings > innerfidelity > crinacle > others
        let sortedOthers = pool.filter { !seenPaths.contains($0.relativePath) }.sorted { a, b in
            func providerRank(_ p: String) -> Int {
                let low = p.lowercased()
                if low.contains("oratory") { return 100 }
                if low.contains("rtings") { return 80 }
                if low.contains("innerfidelity") { return 60 }
                if low.contains("crinacle") { return 40 }
                return 10
            }
            return providerRank(a.provider) > providerRank(b.provider)
        }

        for other in sortedOthers {
            if !seenPaths.contains(other.relativePath) {
                seenPaths.insert(other.relativePath)
                ordered.append(other)
            }
        }

        return ordered
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

        let baseRel = rel.hasPrefix("results/") ? String(rel.dropFirst("results/".count)) : rel
        let folder = baseRel.split(separator: "/").last.map(String.init) ?? ""
        let names = [folder, entry.name].filter { !$0.isEmpty }

        for name in names {
            add("results/\(baseRel)/\(name).csv")
        }

        let parts = baseRel.split(separator: "/").map(String.init)
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

    public static func candidateUrls(for relPath: String) -> [URL] {
        var allowed = CharacterSet.urlPathAllowed
        allowed.remove(charactersIn: "&+?#")
        let escapedPath = relPath.addingPercentEncoding(withAllowedCharacters: allowed) ?? relPath

        var urls: [URL] = []
        // 1. jsDelivr (global CDN, fast & reliable)
        if let u = URL(string: "https://cdn.jsdelivr.net/gh/jaakkopasanen/AutoEq@master/\(escapedPath)") {
            urls.append(u)
        }
        // 2. jsdmirror (China-accelerated mirror)
        if let u = URL(string: "https://cdn.jsdmirror.com/gh/jaakkopasanen/AutoEq@master/\(escapedPath)") {
            urls.append(u)
        }
        // 3. ghfast proxy
        if let u = URL(string: "https://ghfast.top/https://raw.githubusercontent.com/jaakkopasanen/AutoEq/master/\(escapedPath)") {
            urls.append(u)
        }
        // 4. Raw GitHub direct
        if let u = URL(string: "https://raw.githubusercontent.com/jaakkopasanen/AutoEq/master/\(escapedPath)") {
            urls.append(u)
        }
        return urls
    }

    @discardableResult
    public static func fetchCSVWithDetails(for entry: HeadphoneEntry) async throws -> (freqs: [Double], mags: [Double], usedEntry: HeadphoneEntry) {
        let candidates = providerCandidates(for: entry)
        let cacheDir = getCacheDir()
        let desktopFallbackDir = URL(fileURLWithPath: "/Users/zhuyongfei/Desktop/eq_cosplay/offline_csvs")

        // 1. Check local cache across all candidates first
        for candidate in candidates {
            let specificCache = cacheDir.appendingPathComponent("\(safeFilename(for: "\(candidate.name)_\(candidate.provider)")).csv")
            if FileManager.default.fileExists(atPath: specificCache.path),
               let data = try? Data(contentsOf: specificCache),
               let parsed = parseCSVData(data) {
                return (parsed.freqs, parsed.mags, candidate)
            }

            let genericCache = cacheDir.appendingPathComponent("\(safeFilename(for: candidate.name)).csv")
            if FileManager.default.fileExists(atPath: genericCache.path),
               let data = try? Data(contentsOf: genericCache),
               let parsed = parseCSVData(data) {
                return (parsed.freqs, parsed.mags, candidate)
            }

            let desktopSpecific = desktopFallbackDir.appendingPathComponent("\(safeFilename(for: "\(candidate.name)_\(candidate.provider)")).csv")
            if FileManager.default.fileExists(atPath: desktopSpecific.path),
               let data = try? Data(contentsOf: desktopSpecific),
               let parsed = parseCSVData(data) {
                try? data.write(to: specificCache)
                return (parsed.freqs, parsed.mags, candidate)
            }
        }

        // 2. Try downloading via CDN & mirrors for each candidate
        var lastError: Error?

        for candidate in candidates {
            let candidateRelPaths = candidatePaths(for: candidate)
            let cacheFile = cacheDir.appendingPathComponent("\(safeFilename(for: "\(candidate.name)_\(candidate.provider)")).csv")

            for relPath in candidateRelPaths {
                let urls = candidateUrls(for: relPath)
                for url in urls {
                    var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 6.0)
                    request.setValue("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36", forHTTPHeaderField: "User-Agent")

                    do {
                        let (data, response) = try await URLSession.shared.data(for: request)
                        if let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode),
                           let parsed = parseCSVData(data) {
                            try? data.write(to: cacheFile)
                            return (parsed.freqs, parsed.mags, candidate)
                        }
                    } catch {
                        lastError = error
                    }
                }
            }
        }

        throw lastError ?? NSError(
            domain: "CSVFetcher",
            code: -1,
            userInfo: [NSLocalizedDescriptionKey: "Failed to download CSV for \(entry.name) (tried \(candidates.count) providers)"]
        )
    }

    public static func fetchCSV(for entry: HeadphoneEntry) async throws -> (freqs: [Double], mags: [Double]) {
        let (freqs, mags, _) = try await fetchCSVWithDetails(for: entry)
        return (freqs, mags)
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
