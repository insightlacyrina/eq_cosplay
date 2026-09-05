import Foundation

public enum PresetsManager {
    public static func getPresetsDirectory() -> URL {
        let cwdPresets = URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent("presets", isDirectory: true)
        if FileManager.default.fileExists(atPath: cwdPresets.path) && FileManager.default.isWritableFile(atPath: cwdPresets.path) {
            return cwdPresets
        }
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let dir = appSupport.appendingPathComponent("EQ Cosplay/presets", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    public static func listPresets() -> [PresetInfo] {
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let appSupportPresets = appSupport.appendingPathComponent("EQ Cosplay/presets", isDirectory: true)
        let cwdPresets = URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent("presets", isDirectory: true)
        let parentPresets = Bundle.main.bundleURL.deletingLastPathComponent().appendingPathComponent("presets", isDirectory: true)

        var searchDirs = [
            getPresetsDirectory(),
            appSupportPresets,
            cwdPresets,
            parentPresets
        ]

        if let bundlePresets = Bundle.main.resourceURL?.appendingPathComponent("presets", isDirectory: true),
           FileManager.default.fileExists(atPath: bundlePresets.path) {
            searchDirs.append(bundlePresets)
        }

        if let env = ProcessInfo.processInfo.environment["EQ_COSPLAY_PRESETS"] {
            searchDirs.insert(URL(fileURLWithPath: env), at: 0)
        }

        var presets: [PresetInfo] = []
        var seenNames = Set<String>()

        for dir in searchDirs {
            guard let files = try? FileManager.default.contentsOfDirectory(
                at: dir,
                includingPropertiesForKeys: [.contentModificationDateKey],
                options: [.skipsHiddenFiles]
            ) else { continue }

            for file in files {
                let ext = file.pathExtension.lowercased()
                guard ext == "yml" || ext == "yaml" else { continue }

                let stem = file.deletingPathExtension().lastPathComponent
                if seenNames.contains(stem) { continue }
                seenNames.insert(stem)

                let modDate = (try? file.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate ?? Date()

                // Inspect metrics & FIR
                var metrics: [String: Double] = [:]
                var hasFir = false

                if let content = try? String(contentsOf: file, encoding: .utf8) {
                    let lines = content.components(separatedBy: .newlines)
                    if let first = lines.first, first.hasPrefix("# eq_cosplay_metrics:") {
                        let jsonStr = String(first.dropFirst("# eq_cosplay_metrics:".count)).trimmingCharacters(in: .whitespaces)
                        if let data = jsonStr.data(using: .utf8),
                           let dict = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                            for (k, v) in dict {
                                if let d = v as? Double {
                                    metrics[k] = d
                                } else if let b = v as? Bool {
                                    metrics[k] = b ? 1.0 : 0.0
                                }
                            }
                        }
                    }
                    if content.contains("fir_left:") || content.contains("type: Conv") {
                        hasFir = true
                    }
                }

                // Check companion wav files
                let leftWav = file.deletingPathExtension().deletingLastPathComponent().appendingPathComponent("\(stem)_fir_left.wav")
                if FileManager.default.fileExists(atPath: leftWav.path) {
                    hasFir = true
                }

                // Parse display names from filename
                var displayName = stem
                if displayName.hasPrefix("cosplay_") {
                    displayName = String(displayName.dropFirst("cosplay_".count))
                }
                let components = displayName.components(separatedBy: "_to_")
                let sourceName = components.first?.replacingOccurrences(of: "_", with: " ") ?? stem
                let targetName = components.count > 1 ? components[1].replacingOccurrences(of: "_", with: " ") : ""

                let formattedName = components.count > 1 ? "\(sourceName) → \(targetName)" : displayName.replacingOccurrences(of: "_", with: " ")

                presets.append(PresetInfo(
                    name: formattedName,
                    path: file,
                    sourceName: sourceName,
                    targetName: targetName,
                    hasFir: hasFir,
                    metrics: metrics,
                    modifiedDate: modDate
                ))
            }
        }

        presets.sort { $0.modifiedDate > $1.modifiedDate }
        return presets
    }

    public static func savePreset(
        source: HeadphoneEntry,
        target: HeadphoneEntry,
        bands: [PEQBand],
        outputDeviceName: String,
        sampleRate: Int,
        preampGain: Double,
        firIr: [Double]? = nil,
        metrics: [String: Double]? = nil
    ) throws -> URL {
        let dir = getPresetsDirectory()
        let safeSource = CSVFetcher.safeFilename(for: "\(source.name)_\(source.provider)")
        let safeTarget = CSVFetcher.safeFilename(for: "\(target.name)_\(target.provider)")
        let filename = "cosplay_\(safeSource)_to_\(safeTarget)"

        let yamlFile = dir.appendingPathComponent("\(filename).yml")

        var leftPath: String? = nil
        var rightPath: String? = nil

        if let ir = firIr, !ir.isEmpty {
            let leftUrl = dir.appendingPathComponent("\(filename)_fir_left.wav")
            let rightUrl = dir.appendingPathComponent("\(filename)_fir_right.wav")
            let floatSamples = ir.map { Float($0) }
            try WavWriter.writeFloat32Wav(url: leftUrl, samples: floatSamples, sampleRate: sampleRate)
            try WavWriter.writeFloat32Wav(url: rightUrl, samples: floatSamples, sampleRate: sampleRate)
            leftPath = leftUrl.path
            rightPath = rightUrl.path
        }

        let yaml = CamillaDSPConfig.generateYAML(
            bands: bands,
            outputDeviceName: outputDeviceName,
            captureDeviceName: "BlackHole 2ch",
            sampleRate: sampleRate,
            preampGain: preampGain,
            firLeftPath: leftPath,
            firRightPath: rightPath,
            metrics: metrics
        )

        try yaml.write(to: yamlFile, atomically: true, encoding: .utf8)
        return yamlFile
    }

    public static func deletePreset(_ preset: PresetInfo) {
        try? FileManager.default.removeItem(at: preset.path)
        let stem = preset.path.deletingPathExtension().lastPathComponent
        let dir = preset.path.deletingLastPathComponent()
        let leftWav = dir.appendingPathComponent("\(stem)_fir_left.wav")
        let rightWav = dir.appendingPathComponent("\(stem)_fir_right.wav")
        try? FileManager.default.removeItem(at: leftWav)
        try? FileManager.default.removeItem(at: rightWav)
    }

    /// Updates playback.device in the preset YAML to match the user's currently selected physical device,
    /// writing to active_camilla_config.yml in Application Support before starting CamillaDSP.
    public static func preparePresetForLaunch(presetURL: URL, outputDeviceName: String) throws -> URL {
        let rawText = try String(contentsOf: presetURL, encoding: .utf8)
        let pattern = try NSRegularExpression(
            pattern: #"(playback:\s*\n(?:[ \t]+[^\n]+\n)*?[ \t]+device:\s*)(?:"[^"]*"|'[^']*'|[^\n]+)"#,
            options: []
        )
        let range = NSRange(rawText.startIndex..<rawText.endIndex, in: rawText)
        let updatedText = pattern.stringByReplacingMatches(
            in: rawText,
            options: [],
            range: range,
            withTemplate: "$1\"\(outputDeviceName)\""
        )

        var finalText = updatedText
        if !finalText.contains("enable_rate_adjust:") {
            finalText = finalText.replacingOccurrences(
                of: "devices:\n",
                with: "devices:\n  enable_rate_adjust: true\n  resampler:\n    type: Synchronous\n"
            )
        }

        // Dynamically fix companion WAV paths if they exist locally
        let stem = presetURL.deletingPathExtension().lastPathComponent
        let presetDir = presetURL.deletingLastPathComponent()
        let localLeftWav = presetDir.appendingPathComponent("\(stem)_fir_left.wav")
        let localRightWav = presetDir.appendingPathComponent("\(stem)_fir_right.wav")

        if FileManager.default.fileExists(atPath: localLeftWav.path) {
            if let firLeftPattern = try? NSRegularExpression(pattern: #"fir_left:\s*\n([ \t]+type:\s*Conv\s*\n[ \t]+parameters:\s*\n(?:[ \t]+[^\n]+\n)*?[ \t]+filename:\s*)(?:"[^"]*"|'[^']*'|[^\n]+)"#, options: []) {
                let r = NSRange(finalText.startIndex..<finalText.endIndex, in: finalText)
                finalText = firLeftPattern.stringByReplacingMatches(in: finalText, options: [], range: r, withTemplate: "$1\"\(localLeftWav.path)\"")
            }
        }
        if FileManager.default.fileExists(atPath: localRightWav.path) {
            if let firRightPattern = try? NSRegularExpression(pattern: #"fir_right:\s*\n([ \t]+type:\s*Conv\s*\n[ \t]+parameters:\s*\n(?:[ \t]+[^\n]+\n)*?[ \t]+filename:\s*)(?:"[^"]*"|'[^']*'|[^\n]+)"#, options: []) {
                let r = NSRange(finalText.startIndex..<finalText.endIndex, in: finalText)
                finalText = firRightPattern.stringByReplacingMatches(in: finalText, options: [], range: r, withTemplate: "$1\"\(localRightWav.path)\"")
            }
        }

        let dir = getPresetsDirectory()
        let activeLaunchURL = dir.appendingPathComponent("active_camilla_config.yml")
        try finalText.write(to: activeLaunchURL, atomically: true, encoding: .utf8)
        return activeLaunchURL
    }

    public struct PresetDetails: Sendable {
        public let bands: [PEQBand]
        public let firIr: [Double]?
        public let metrics: [String: Double]
        public let preampGain: Double
        public let sampleRate: Int
        public let hasFir: Bool

        public init(
            bands: [PEQBand],
            firIr: [Double]?,
            metrics: [String: Double],
            preampGain: Double,
            sampleRate: Int,
            hasFir: Bool
        ) {
            self.bands = bands
            self.firIr = firIr
            self.metrics = metrics
            self.preampGain = preampGain
            self.sampleRate = sampleRate
            self.hasFir = hasFir
        }
    }

    public static func loadPresetDetails(from url: URL) -> PresetDetails? {
        guard let content = try? String(contentsOf: url, encoding: .utf8) else { return nil }
        let parsed = CamillaDSPConfig.parseYAML(content)

        var firIr: [Double]? = nil
        let stem = url.deletingPathExtension().lastPathComponent
        let dir = url.deletingLastPathComponent()
        let leftWav = dir.appendingPathComponent("\(stem)_fir_left.wav")

        var targetWav = leftWav
        if !FileManager.default.fileExists(atPath: targetWav.path), let p = parsed.firLeftPath {
            let altUrl = URL(fileURLWithPath: p)
            if FileManager.default.fileExists(atPath: altUrl.path) {
                targetWav = altUrl
            }
        }

        if FileManager.default.fileExists(atPath: targetWav.path) {
            if let data = try? Data(contentsOf: targetWav) {
                // Find "data" chunk
                if let dataMarker = data.range(of: Data("data".utf8)) {
                    let payloadStart = dataMarker.upperBound + 4
                    if payloadStart < data.count {
                        let payload = data.subdata(in: payloadStart..<data.count)
                        var doubles: [Double] = []
                        payload.withUnsafeBytes { raw in
                            let floats = raw.bindMemory(to: Float.self)
                            doubles = floats.map { Double($0) }
                        }
                        if !doubles.isEmpty {
                            firIr = doubles
                        }
                    }
                }
            }
        }

        return PresetDetails(
            bands: parsed.bands,
            firIr: firIr,
            metrics: parsed.metrics,
            preampGain: parsed.preampGain,
            sampleRate: parsed.sampleRate,
            hasFir: parsed.useFir || (firIr != nil && !(firIr!.isEmpty))
        )
    }

}
