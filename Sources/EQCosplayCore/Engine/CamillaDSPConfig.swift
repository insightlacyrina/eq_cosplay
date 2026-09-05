import Foundation

public enum CamillaDSPConfig {
    public static func generateYAML(
        bands: [PEQBand],
        outputDeviceName: String,
        captureDeviceName: String = "BlackHole 2ch",
        sampleRate: Int = 48000,
        preampGain: Double = 0.0,
        firLeftPath: String? = nil,
        firRightPath: String? = nil,
        metrics: [String: Double]? = nil
    ) -> String {
        var yaml = ""

        // Header metrics comment
        if let m = metrics {
            if let data = try? JSONSerialization.data(withJSONObject: m, options: [.sortedKeys]),
               let jsonStr = String(data: data, encoding: .utf8) {
                yaml += "# eq_cosplay_metrics: \(jsonStr)\n"
            }
        }

        yaml += """
        ---
        devices:
          samplerate: \(sampleRate)
          chunksize: 1024
          enable_rate_adjust: true
          resampler:
            type: Synchronous
          capture:
            type: CoreAudio
            channels: 2
            device: "\(captureDeviceName)"
          playback:
            type: CoreAudio
            channels: 2
            device: "\(outputDeviceName)"


        filters:

        """

        if abs(preampGain) > 1e-4 {
            yaml += """
              preamp_gain:
                type: Gain
                parameters:
                  gain: \(preampGain)
                  inverted: false


            """
        }

        if let left = firLeftPath, let right = firRightPath {
            yaml += """
              fir_left:
                type: Conv
                parameters:
                  type: Wav
                  filename: "\(left)"
                  channel: 0

              fir_right:
                type: Conv
                parameters:
                  type: Wav
                  filename: "\(right)"
                  channel: 0


            """
        }

        for (i, b) in bands.enumerated() {
            let name = String(format: "peq_%02d", i + 1)
            yaml += """
              \(name):
                type: Biquad
                parameters:
                  type: \(b.type.rawValue)
                  freq: \(b.frequency)
                  gain: \(b.gain)
                  q: \(b.q)

            """
        }

        let peqNames = (1...bands.count).map { String(format: "peq_%02d", $0) }

        yaml += "\npipeline:\n"

        if firLeftPath != nil {
            for (ch, firName) in [(0, "fir_left"), (1, "fir_right")] {
                yaml += """
                  - type: Filter
                    channels: [\(ch)]
                    names:

                """
                if abs(preampGain) > 1e-4 {
                    yaml += "      - preamp_gain\n"
                }
                yaml += "      - \(firName)\n"
                for pName in peqNames {
                    yaml += "      - \(pName)\n"
                }
            }
        } else {
            yaml += """
              - type: Filter
                channels: [0, 1]
                names:

            """
            if abs(preampGain) > 1e-4 {
                yaml += "      - preamp_gain\n"
            }
            for pName in peqNames {
                yaml += "      - \(pName)\n"
            }
        }

        return yaml
    }

    public struct ParsedConfig: Sendable {
        public let bands: [PEQBand]
        public let sampleRate: Int
        public let preampGain: Double
        public let firLeftPath: String?
        public let firRightPath: String?
        public let metrics: [String: Double]
        public let useFir: Bool

        public init(
            bands: [PEQBand],
            sampleRate: Int = 48000,
            preampGain: Double = 0.0,
            firLeftPath: String? = nil,
            firRightPath: String? = nil,
            metrics: [String: Double] = [:],
            useFir: Bool = false
        ) {
            self.bands = bands
            self.sampleRate = sampleRate
            self.preampGain = preampGain
            self.firLeftPath = firLeftPath
            self.firRightPath = firRightPath
            self.metrics = metrics
            self.useFir = useFir
        }
    }

    public static func parseYAML(_ yaml: String) -> ParsedConfig {
        var metrics: [String: Double] = [:]
        var sampleRate: Int = 48000
        var preampGain: Double = 0.0
        var firLeftPath: String? = nil
        var firRightPath: String? = nil
        var bands: [PEQBand] = []

        let lines = yaml.components(separatedBy: .newlines)
        for line in lines {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.hasPrefix("# eq_cosplay_metrics:") {
                let jsonStr = String(trimmed.dropFirst("# eq_cosplay_metrics:".count)).trimmingCharacters(in: .whitespaces)
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
        }

        // Sample rate
        if let match = yaml.range(of: #"samplerate:\s*(\d+)"#, options: .regularExpression) {
            let sub = yaml[match]
            let digits = sub.components(separatedBy: CharacterSet.decimalDigits.inverted).joined()
            if let sr = Int(digits) {
                sampleRate = sr
            }
        }

        // Preamp gain
        if let match = yaml.range(of: #"preamp_gain:[\s\S]*?gain:\s*([+-]?\d+(?:\.\d+)?)"#, options: .regularExpression) {
            let sub = String(yaml[match])
            if let gMatch = sub.range(of: #"gain:\s*([+-]?\d+(?:\.\d+)?)"#, options: .regularExpression) {
                let gSub = sub[gMatch].replacingOccurrences(of: "gain:", with: "").trimmingCharacters(in: .whitespaces)
                if let val = Double(gSub) {
                    preampGain = val
                }
            }
        }

        // FIR paths (supports fir_left, fir_corr, fir, quoted or unquoted)
        if let match = yaml.range(of: #"(?:fir_left|fir_corr|fir):[\s\S]*?filename:\s*"*([^"\r\n]+)"*"#, options: .regularExpression) {
            let sub = String(yaml[match])
            if let fMatch = sub.range(of: #"filename:\s*"*([^"\r\n]+)"*"#, options: .regularExpression) {
                var p = String(sub[fMatch])
                p = p.replacingOccurrences(of: "filename:", with: "").replacingOccurrences(of: "\"", with: "").trimmingCharacters(in: .whitespaces)
                firLeftPath = p
            }
        }
        if let match = yaml.range(of: #"fir_right:[\s\S]*?filename:\s*"*([^"\r\n]+)"*"#, options: .regularExpression) {
            let sub = String(yaml[match])
            if let fMatch = sub.range(of: #"filename:\s*"*([^"\r\n]+)"*"#, options: .regularExpression) {
                var p = String(sub[fMatch])
                p = p.replacingOccurrences(of: "filename:", with: "").replacingOccurrences(of: "\"", with: "").trimmingCharacters(in: .whitespaces)
                firRightPath = p
            }
        }

        // Check if pipeline actually uses FIR
        let useFir = (yaml.contains("fir_left") || yaml.contains("fir_corr")) && yaml.contains("pipeline:") && (yaml.contains("- fir_left") || yaml.contains("- fir_corr"))

        // Parse PEQ bands block by block
        var currentBandFreq: Double? = nil
        var currentBandGain: Double? = nil
        var currentBandQ: Double? = nil
        var currentBandType: FilterType = .peaking
        var inPeqBlock = false

        func commitCurrentBand() {
            if inPeqBlock, let f = currentBandFreq, let g = currentBandGain, let q = currentBandQ {
                bands.append(PEQBand(type: currentBandType, frequency: f, gain: g, q: q))
            }
            currentBandFreq = nil
            currentBandGain = nil
            currentBandQ = nil
            currentBandType = .peaking
            inPeqBlock = false
        }

        for line in lines {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.range(of: #"^peq_\d+:"#, options: .regularExpression) != nil {
                commitCurrentBand()
                inPeqBlock = true
                continue
            }

            if inPeqBlock {
                let leadingSpaces = line.prefix(while: { $0 == " " }).count
                if leadingSpaces <= 2 && trimmed.contains(":") && !trimmed.hasPrefix("peq_") {
                    commitCurrentBand()
                    continue
                }

                if trimmed.hasPrefix("freq:") || trimmed.hasPrefix("frequency:") {
                    let parts = trimmed.components(separatedBy: ":")
                    if parts.count >= 2, let v = Double(parts[1].trimmingCharacters(in: .whitespaces)) {
                        currentBandFreq = v
                    }
                } else if trimmed.hasPrefix("gain:") {
                    let parts = trimmed.components(separatedBy: ":")
                    if parts.count >= 2, let v = Double(parts[1].trimmingCharacters(in: .whitespaces)) {
                        currentBandGain = v
                    }
                } else if trimmed.hasPrefix("q:") {
                    let parts = trimmed.components(separatedBy: ":")
                    if parts.count >= 2, let v = Double(parts[1].trimmingCharacters(in: .whitespaces)) {
                        currentBandQ = v
                    }
                } else if trimmed.hasPrefix("type:") {
                    let parts = trimmed.components(separatedBy: ":")
                    if parts.count >= 2 {
                        let t = parts[1].trimmingCharacters(in: .whitespaces).lowercased()
                        if t.contains("low") {
                            currentBandType = .lowshelf
                        } else if t.contains("high") {
                            currentBandType = .highshelf
                        } else if t.contains("peak") {
                            currentBandType = .peaking
                        }
                    }
                }
            }
        }
        commitCurrentBand()

        return ParsedConfig(
            bands: bands,
            sampleRate: sampleRate,
            preampGain: preampGain,
            firLeftPath: firLeftPath,
            firRightPath: firRightPath,
            metrics: metrics,
            useFir: useFir
        )
    }
}
