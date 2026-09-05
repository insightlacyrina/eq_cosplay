import Foundation

public enum PresetsManager {
    public static func getPresetsDirectory() -> URL {
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let dir = appSupport.appendingPathComponent("EQ Cosplay/presets", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    public static func listPresets() -> [PresetInfo] {
        var searchDirs = [
            getPresetsDirectory(),
            URL(fileURLWithPath: "/Users/zhuyongfei/Desktop/eq_cosplay/presets"),
            URL(fileURLWithPath: "/Users/zhuyongfei/Desktop/eq_cosplay_swift/presets")
        ]

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
}
