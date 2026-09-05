import Foundation

public final class AutoEqService: @unchecked Sendable {
    public static let shared = AutoEqService()

    public static let indexRawUrl = "https://raw.githubusercontent.com/jaakkopasanen/AutoEq/master/results/INDEX.md"
    public static let mirrorIndexUrl = "https://ghfast.top/https://raw.githubusercontent.com/jaakkopasanen/AutoEq/master/results/INDEX.md"

    public private(set) var database: [String: [HeadphoneEntry]] = [:]
    public private(set) var isLoaded = false

    private init() {
        // Pre-populate with essential fallback models
        self.database = Self.builtinFallbackEntries
    }

    public static func getCacheDir() -> URL {
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let dir = appSupport.appendingPathComponent("EQ Cosplay", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    public func loadDatabase() async {
        let cacheFile = Self.getCacheDir().appendingPathComponent("INDEX.md")

        // 1. Try reading existing local cached INDEX.md
        if FileManager.default.fileExists(atPath: cacheFile.path),
           let cachedText = try? String(contentsOf: cacheFile, encoding: .utf8) {
            let parsed = IndexParser.parseAutoEqIndex(rawText: cachedText)
            if !parsed.isEmpty {
                self.database = parsed
                self.isLoaded = true
            }
        }

        // 2. Fetch fresh index in background
        let urls = [Self.indexRawUrl, Self.mirrorIndexUrl]
        for urlStr in urls {
            guard let url = URL(string: urlStr) else { continue }
            var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 15.0)
            request.setValue("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36", forHTTPHeaderField: "User-Agent")

            do {
                let (data, response) = try await URLSession.shared.data(for: request)
                if let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode),
                   let text = String(data: data, encoding: .utf8) {
                    let parsed = IndexParser.parseAutoEqIndex(rawText: text)
                    if !parsed.isEmpty {
                        self.database = parsed
                        self.isLoaded = true
                        try? data.write(to: cacheFile)
                        return
                    }
                }
            } catch {
                continue
            }
        }

        if self.database.isEmpty {
            self.database = Self.builtinFallbackEntries
            self.isLoaded = true
        }
    }

    public func search(query: String, limit: Int = 30) -> [HeadphoneEntry] {
        HeadphoneMatcher.search(query: query, in: database, limit: limit)
    }

    public static let builtinFallbackEntries: [String: [HeadphoneEntry]] = [
        "sony wh-1000xm4": [
            HeadphoneEntry(name: "Sony WH-1000XM4", form: "over-ear", rig: "oratory1990", provider: "oratory1990", relativePath: "oratory1990/over-ear/Sony WH-1000XM4"),
            HeadphoneEntry(name: "Sony WH-1000XM4", form: "over-ear", rig: "rtings", provider: "rtings", relativePath: "rtings/rtings_harman_over-ear_2018/Sony WH-1000XM4")
        ],
        "akg q701": [
            HeadphoneEntry(name: "AKG Q701", form: "over-ear", rig: "oratory1990", provider: "oratory1990", relativePath: "oratory1990/over-ear/AKG Q701"),
            HeadphoneEntry(name: "AKG Q701", form: "over-ear", rig: "innerfidelity", provider: "innerfidelity", relativePath: "innerfidelity/innerfidelity_harman_over-ear_2018/AKG Q701")
        ],
        "sennheiser hd 600": [
            HeadphoneEntry(name: "Sennheiser HD 600", form: "over-ear", rig: "oratory1990", provider: "oratory1990", relativePath: "oratory1990/over-ear/Sennheiser HD 600"),
            HeadphoneEntry(name: "Sennheiser HD 600", form: "over-ear", rig: "crinacle", provider: "crinacle", relativePath: "crinacle/crinacle_harman_over-ear_2018/Sennheiser HD 600")
        ],
        "sennheiser hd 650": [
            HeadphoneEntry(name: "Sennheiser HD 650", form: "over-ear", rig: "oratory1990", provider: "oratory1990", relativePath: "oratory1990/over-ear/Sennheiser HD 650")
        ],
        "sennheiser hd 800 s": [
            HeadphoneEntry(name: "Sennheiser HD 800 S", form: "over-ear", rig: "oratory1990", provider: "oratory1990", relativePath: "oratory1990/over-ear/Sennheiser HD 800 S")
        ],
        "apple airpods pro 2": [
            HeadphoneEntry(name: "Apple AirPods Pro 2", form: "in-ear", rig: "crinacle", provider: "crinacle", relativePath: "crinacle/crinacle_harman_in-ear_2019v2/Apple AirPods Pro 2")
        ],
        "apple airpods max": [
            HeadphoneEntry(name: "Apple AirPods Max", form: "over-ear", rig: "oratory1990", provider: "oratory1990", relativePath: "oratory1990/over-ear/Apple AirPods Max")
        ],
        "audio-technica ath-m50x": [
            HeadphoneEntry(name: "Audio-Technica ATH-M50x", form: "over-ear", rig: "oratory1990", provider: "oratory1990", relativePath: "oratory1990/over-ear/Audio-Technica ATH-M50x")
        ],
        "hifiman sundara": [
            HeadphoneEntry(name: "Hifiman Sundara", form: "over-ear", rig: "oratory1990", provider: "oratory1990", relativePath: "oratory1990/over-ear/Hifiman Sundara (2020 revised earpads)")
        ],
        "beyerdynamic dt 770 pro 80 ohm": [
            HeadphoneEntry(name: "Beyerdynamic DT 770 Pro 80 Ohm", form: "over-ear", rig: "oratory1990", provider: "oratory1990", relativePath: "oratory1990/over-ear/Beyerdynamic DT 770 Pro (80 Ohm)")
        ]
    ]
}
