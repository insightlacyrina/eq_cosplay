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
}
