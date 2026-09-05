import Foundation
import EQCosplayCore

@main
struct EQCosplayCLI {
    static func main() async {
        print("""
        ===========================================================
                      EQ Cosplay (Swift Native Edition)
               让一副耳机“扮演”另一副耳机的听感 — AutoEq + CamillaDSP
        ===========================================================
        """)

        // 1. Detect audio devices
        let devices = CoreAudioService.getAudioOutputDevices()
        let defaultDevice = devices.first { $0.isDefault } ?? devices.first
        print("[INFO] Detected \(devices.count) output audio device(s). Default: \(defaultDevice?.name ?? "None")")

        let hasBlackHole = BlackHoleManager.isBlackHoleInstalled()
        if !hasBlackHole {
            print("[WARN] BlackHole 2ch was not found. System-wide filtering requires a virtual audio loopback device.")
        }

        // 2. Check existing presets
        let savedPresets = PresetsManager.listPresets()
        if !savedPresets.isEmpty {
            print("\n[INFO] Found \(savedPresets.count) locally saved preset(s):")
            for (idx, p) in savedPresets.prefix(8).enumerated() {
                print("  [\(idx + 1)] \(p.name) \(p.hasFir ? "[FIR]" : "")")
            }
            print("  [0] Create a new cosplay pairing")
            print("Select preset number to deploy, or 0 to continue: ", terminator: "")

            if let input = readLine()?.trimmingCharacters(in: .whitespacesAndNewlines),
               let num = Int(input), num > 0 && num <= min(savedPresets.count, 8) {
                let selected = savedPresets[num - 1]
                let outName = defaultDevice?.name ?? "Headphones"
                print("[..] Deploying preset: \(selected.name) to output: \(outName)...")
                do {
                    let activeURL = try PresetsManager.preparePresetForLaunch(presetURL: selected.path, outputDeviceName: outName)
                    try CamillaProcess.shared.start(configPath: activeURL)
                    print("[OK] CamillaDSP running. Press Enter to stop.")
                    _ = readLine()
                    CamillaProcess.shared.stop()
                    print("[INFO] Engine stopped. Goodbye!")
                    return
                } catch {
                    print("[ERR] Failed to start CamillaDSP: \(error.localizedDescription)")
                }
            }
        }

        // 3. Load AutoEq database
        print("\n[..] Connecting to AutoEq GitHub database...")
        await AutoEqService.shared.loadDatabase()
        print("[OK] Loaded \(AutoEqService.shared.database.count) headphone models.")

        // 4. Select Source Headphone
        var sourceEntry: HeadphoneEntry? = nil
        while sourceEntry == nil {
            print("\nStep 1: Enter your CURRENT headphone model (or 'q' to quit): ", terminator: "")
            guard let line = readLine()?.trimmingCharacters(in: .whitespacesAndNewlines), !line.isEmpty else { continue }
            if line.lowercased() == "q" { return }

            let matches = AutoEqService.shared.search(query: line, limit: 5)
            if matches.isEmpty {
                print("[ERR] No matches found for '\(line)'. Try a different keyword.")
                continue
            }

            if matches.count == 1 {
                sourceEntry = matches[0]
            } else {
                print("Matches:")
                for (i, m) in matches.enumerated() {
                    print("  [\(i + 1)] \(m.name) (\(m.provider) - \(m.rig))")
                }
                print("Select number (1-\(matches.count)): ", terminator: "")
                if let pick = readLine()?.trimmingCharacters(in: .whitespacesAndNewlines),
                   let idx = Int(pick), idx >= 1 && idx <= matches.count {
                    sourceEntry = matches[idx - 1]
                }
            }
        }

        // 5. Select Target Headphone
        var targetEntry: HeadphoneEntry? = nil
        while targetEntry == nil {
            print("\nStep 2: Enter the TARGET headphone you want to mimic (or 'q' to quit): ", terminator: "")
            guard let line = readLine()?.trimmingCharacters(in: .whitespacesAndNewlines), !line.isEmpty else { continue }
            if line.lowercased() == "q" { return }

            let matches = AutoEqService.shared.search(query: line, limit: 5)
            if matches.isEmpty {
                print("[ERR] No matches found for '\(line)'. Try a different keyword.")
                continue
            }

            if matches.count == 1 {
                targetEntry = matches[0]
            } else {
                print("Matches:")
                for (i, m) in matches.enumerated() {
                    print("  [\(i + 1)] \(m.name) (\(m.provider) - \(m.rig))")
                }
                print("Select number (1-\(matches.count)): ", terminator: "")
                if let pick = readLine()?.trimmingCharacters(in: .whitespacesAndNewlines),
                   let idx = Int(pick), idx >= 1 && idx <= matches.count {
                    targetEntry = matches[idx - 1]
                }
            }
        }

        guard let src = sourceEntry, let tgt = targetEntry else { return }

        // 6. Download CSVs
        print("\n[..] Downloading measurement CSV for Source: \(src.name)...")
        guard let (srcFreqs, srcMags) = try? await CSVFetcher.fetchCSV(for: src) else {
            print("[ERR] Failed to download CSV for \(src.name).")
            return
        }

        print("[..] Downloading measurement CSV for Target: \(tgt.name)...")
        guard let (tgtFreqs, tgtMags) = try? await CSVFetcher.fetchCSV(for: tgt) else {
            print("[ERR] Failed to download CSV for \(tgt.name).")
            return
        }

        // 7. Calculate 10-band IIR PEQ + FIR
        let sampleRate = 48000
        print("\n[..] Calculating correction curves at \(sampleRate) Hz...")
        let result = CorrectionEngine.calculateCorrection(
            sourceFreqs: srcFreqs,
            sourceMags: srcMags,
            targetFreqs: tgtFreqs,
            targetMags: tgtMags,
            fs: Double(sampleRate)
        )

        // 8. Display Results
        print("\n----------------- 10-BAND PARAMETRIC EQ -----------------")
        print(String(format: "%-4s %-12s %-12s %-10s %-8s", "#", "Type", "Freq (Hz)", "Gain (dB)", "Q"))
        print("---------------------------------------------------------")
        for (i, b) in result.peqBands.enumerated() {
            print(String(
                format: "%02d   %-12s %-12.1f %+7.2f    %5.2f",
                i + 1,
                b.type.displayName,
                b.frequency,
                b.gain,
                b.q
            ))
        }
        print("---------------------------------------------------------")
        print("IIR 10-Band RMSE:      \(String(format: "%.2f", result.peqRmse)) dB")
        if result.useFir {
            print("FIR Residual Filter:   Enabled (\(result.firTaps) taps)")
            print("Combined + FIR RMSE:   \(String(format: "%.2f", result.combinedRmse)) dB")
        } else {
            print("FIR Residual Filter:   Skipped (IIR within critical tolerance)")
        }
        print("Response Peak:         \(String(format: "%.2f", result.responsePeak)) dB")
        print("Level Alignment:       \(String(format: "%+.2f", result.levelOffsetDb)) dB")

        // 9. Preamp Gain
        let peak = result.responsePeak
        var preamp = 0.0
        if peak > 0 {
            let safe = -(peak + 0.2)
            let moderate = -(peak / 2.0)
            print("\nPreamp Gain Options (to prevent clipping):")
            print("  [1] Safe mode:     \(String(format: "%.2f", safe)) dB (Recommended)")
            print("  [2] Moderate mode: \(String(format: "%.2f", moderate)) dB")
            print("  [3] Custom dB")
            print("  [4] No preamp (0.0 dB)")
            print("Select preamp mode [1-4] (default 1): ", terminator: "")
            let choice = readLine()?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "1"
            switch choice {
            case "2": preamp = moderate
            case "3":
                print("Enter custom preamp in dB: ", terminator: "")
                if let v = readLine()?.trimmingCharacters(in: .whitespacesAndNewlines), let d = Double(v) {
                    preamp = d
                } else {
                    preamp = safe
                }
            case "4": preamp = 0.0
            default: preamp = safe
            }
        }
        print("Applied Preamp Gain: \(String(format: "%.2f", preamp)) dB")

        // 10. Deploy to CamillaDSP
        print("\nDeploy and start CamillaDSP with this preset? (y/n): ", terminator: "")
        let deployChoice = readLine()?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() ?? "y"
        if deployChoice == "y" || deployChoice == "yes" {
            let outName = defaultDevice?.name ?? "Headphones"
            let metrics: [String: Double] = [
                "peq_rmse": result.peqRmse,
                "combined_rmse": result.combinedRmse,
                "response_peak": result.responsePeak,
                "fir_n_taps": Double(result.firTaps),
                "use_fir": result.useFir ? 1.0 : 0.0
            ]

            do {
                let configUrl = try PresetsManager.savePreset(
                    source: src,
                    target: tgt,
                    bands: result.peqBands,
                    outputDeviceName: outName,
                    sampleRate: sampleRate,
                    preampGain: preamp,
                    firIr: result.useFir ? result.firIr : nil,
                    metrics: metrics
                )
                print("[OK] Configuration saved: \(configUrl.path)")
                print("[..] Starting CamillaDSP...")
                try CamillaProcess.shared.start(configPath: configUrl)
                print("\n=======================================================")
                print(" CamillaDSP is now actively playing EQ Cosplay sound!")
                print(" Source:  \(src.name)")
                print(" Target:  \(tgt.name)")
                print(" Routing: BlackHole 2ch -> CamillaDSP -> \(outName)")
                print(" Press Enter to stop engine and exit.")
                print("=======================================================")
                _ = readLine()
                CamillaProcess.shared.stop()
                print("[INFO] CamillaDSP stopped. Have a nice day!")
            } catch {
                print("[ERR] Failed to deploy CamillaDSP: \(error.localizedDescription)")
            }
        } else {
            print("[INFO] Deployment skipped. Preset not loaded.")
        }
    }
}
