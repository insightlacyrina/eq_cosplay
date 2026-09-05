import Foundation
import SwiftUI
import EQCosplayCore

@MainActor
public final class AppState: ObservableObject {
    @Published public var sourceQuery = ""
    @Published public var targetQuery = ""
    @Published public var sourceResults: [HeadphoneEntry] = []
    @Published public var targetResults: [HeadphoneEntry] = []

    @Published public var selectedSource: HeadphoneEntry?
    @Published public var selectedTarget: HeadphoneEntry?

    @Published public var correctionResult: CorrectionResult?
    @Published public var isCalculating = false
    @Published public var isEngineRunning = false
    @Published public var activePresetTitle: String?

    @Published public var outputDevices: [AudioDevice] = []
    @Published public var selectedDevice: AudioDevice?

    @Published public var sampleRate: SupportedSampleRate = .r48000
    @Published public var preampMode: PreampMode = .safe
    @Published public var customPreamp: Double = -3.0

    @Published public var savedPresets: [PresetInfo] = []
    @Published public var logs: [String] = []
    @Published public var isBlackHoleFound = true

    // Active dropdown coordinator: ensures only one dropdown/search popup is open at a time
    @Published public var activeDropdownId: String? = nil

    public init() {
        self.outputDevices = CoreAudioService.getAudioOutputDevices()
        self.selectedDevice = self.outputDevices.first { $0.isDefault } ?? self.outputDevices.first
        self.isBlackHoleFound = BlackHoleManager.isBlackHoleInstalled()
        self.refreshPresets()

        // Hook up CamillaProcess log callback
        CamillaProcess.shared.onLogMessage = { [weak self] message in
            Task { @MainActor in
                self?.appendLog(message)
            }
        }
    }

    // Status string matched to active language
    public func localizedStatus(for language: Language) -> String {
        if isCalculating {
            switch language {
            case .zh: return "计算校正中..."
            case .en: return "Optimizing..."
            case .ja: return "最適化中..."
            }
        } else if isEngineRunning {
            let preset = activePresetTitle ?? ""
            let suffix = preset.isEmpty ? "" : " · \(preset)"
            switch language {
            case .zh: return "DSP 运行中\(suffix)"
            case .en: return "DSP Running\(suffix)"
            case .ja: return "DSP 実行中\(suffix)"
            }
        } else if !isBlackHoleFound {
            switch language {
            case .zh: return "未检测到 BlackHole 虚拟声卡"
            case .en: return "Missing BlackHole Driver"
            case .ja: return "BlackHole 仮想ドライバ未検出"
            }
        } else {
            switch language {
            case .zh: return "就绪"
            case .en: return "Ready"
            case .ja: return "準備完了"
            }
        }
    }

    public func initialLoad() async {
        appendLog("[..] Loading AutoEq database...")
        await AutoEqService.shared.loadDatabase()
        appendLog("[OK] Loaded \(AutoEqService.shared.database.count) headphone models from AutoEq.")
    }

    public func searchSource() {
        guard !sourceQuery.trimmingCharacters(in: .whitespaces).isEmpty else {
            sourceResults = []
            return
        }
        sourceResults = AutoEqService.shared.search(query: sourceQuery, limit: 12)
    }

    public func searchTarget() {
        guard !targetQuery.trimmingCharacters(in: .whitespaces).isEmpty else {
            targetResults = []
            return
        }
        targetResults = AutoEqService.shared.search(query: targetQuery, limit: 12)
    }

    public func calculateCorrection() async {
        guard let source = selectedSource, let target = selectedTarget else {
            appendLog("[!] Please select both source and target headphones.")
            return
        }

        isCalculating = true
        appendLog("[..] Downloading frequency response data for \(source.name) and \(target.name)...")

        do {
            let (srcFreqs, srcMags) = try await CSVFetcher.fetchCSV(for: source)
            let (tgtFreqs, tgtMags) = try await CSVFetcher.fetchCSV(for: target)

            appendLog("[..] Optimizing 10-band PEQ and synthesizing minimum-phase FIR...")
            let result = CorrectionEngine.calculateCorrection(
                sourceFreqs: srcFreqs,
                sourceMags: srcMags,
                targetFreqs: tgtFreqs,
                targetMags: tgtMags,
                fs: Double(sampleRate.rawValue)
            )

            self.correctionResult = result
            let gain = preampMode.calculateGain(peak: result.responsePeak)
            appendLog("[OK] Correction calculated. Preamp: \(String(format: "%.2f", gain)) dB. RMSE: \(String(format: "%.2f", result.peqRmse)) dB.")
        } catch {
            appendLog("[ERR] Correction calculation failed: \(error.localizedDescription)")
        }

        isCalculating = false
    }

    public func deployCamillaDSP() {
        guard let result = correctionResult, let device = selectedDevice else {
            appendLog("[!] Missing correction result or output device.")
            return
        }

        do {
            appendLog("[..] Generating CamillaDSP configuration for \(device.name)...")
            let preampGain = preampMode.calculateGain(peak: result.responsePeak)

            let dir = PresetsManager.getPresetsDirectory()
            let configURL = dir.appendingPathComponent("active_camilla_config.yml")

            var leftPath: String? = nil
            var rightPath: String? = nil

            if let ir = result.firIr, !ir.isEmpty {
                let leftUrl = dir.appendingPathComponent("active_fir_left.wav")
                let rightUrl = dir.appendingPathComponent("active_fir_right.wav")
                let floatSamples = ir.map { Float($0) }
                try WavWriter.writeFloat32Wav(url: leftUrl, samples: floatSamples, sampleRate: sampleRate.rawValue)
                try WavWriter.writeFloat32Wav(url: rightUrl, samples: floatSamples, sampleRate: sampleRate.rawValue)
                leftPath = leftUrl.path
                rightPath = rightUrl.path
            }

            let yaml = CamillaDSPConfig.generateYAML(
                bands: result.peqBands,
                outputDeviceName: device.name,
                captureDeviceName: "BlackHole 2ch",
                sampleRate: sampleRate.rawValue,
                preampGain: preampGain,
                firLeftPath: leftPath,
                firRightPath: rightPath,
                metrics: ["peq_rmse": result.peqRmse, "combined_rmse": result.combinedRmse]
            )

            try yaml.write(to: configURL, atomically: true, encoding: .utf8)

            appendLog("[..] Starting CamillaDSP process...")
            try CamillaProcess.shared.start(configPath: configURL)
            self.isEngineRunning = true
            self.activePresetTitle = "\(selectedSource?.name ?? "") → \(selectedTarget?.name ?? "")"
            appendLog("[OK] CamillaDSP is actively filtering system audio.")
        } catch {
            appendLog("[ERR] Failed to start CamillaDSP: \(error.localizedDescription)")
        }
    }

    public func stopCamillaDSP() {
        CamillaProcess.shared.stop()
        self.isEngineRunning = false
        self.activePresetTitle = nil
        appendLog("[OK] CamillaDSP stopped.")
    }

    public func refreshDevices() {
        self.outputDevices = CoreAudioService.getAudioOutputDevices()
        if selectedDevice == nil || !outputDevices.contains(where: { $0.id == selectedDevice?.id }) {
            self.selectedDevice = outputDevices.first { $0.isDefault } ?? outputDevices.first
        }
        self.isBlackHoleFound = BlackHoleManager.isBlackHoleInstalled()
    }

    public func refreshPresets() {
        self.savedPresets = PresetsManager.listPresets()
    }

    public func loadPreset(_ preset: PresetInfo) {
        appendLog("[..] Loading preset: \(preset.name)...")
        do {
            try CamillaProcess.shared.start(configPath: preset.path)
            self.isEngineRunning = true
            self.activePresetTitle = preset.name
            appendLog("[OK] Preset \(preset.name) activated.")
        } catch {
            appendLog("[ERR] Failed to load preset \(preset.name): \(error.localizedDescription)")
        }
    }

    public func saveCurrentPreset(name: String) {
        guard let result = correctionResult,
              let src = selectedSource,
              let tgt = selectedTarget,
              let device = selectedDevice else { return }

        let preampGain = preampMode.calculateGain(peak: result.responsePeak)

        do {
            _ = try PresetsManager.savePreset(
                source: src,
                target: tgt,
                bands: result.peqBands,
                outputDeviceName: device.name,
                sampleRate: sampleRate.rawValue,
                preampGain: preampGain,
                firIr: result.firIr,
                metrics: ["peq_rmse": result.peqRmse, "combined_rmse": result.combinedRmse]
            )
            refreshPresets()
            appendLog("[OK] Preset '\(name)' saved.")
        } catch {
            appendLog("[ERR] Failed to save preset: \(error.localizedDescription)")
        }
    }

    public func appendLog(_ message: String) {
        let timestamp = ISO8601DateFormatter().string(from: Date()).suffix(12).prefix(8)
        self.logs.append("[\(timestamp)] \(message)")
        if self.logs.count > 200 {
            self.logs.removeFirst(self.logs.count - 200)
        }
    }

    public func clearLogs() {
        self.logs.removeAll()
    }
}
