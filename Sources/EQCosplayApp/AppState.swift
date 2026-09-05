import Foundation
import SwiftUI
import CoreAudio
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
    public var previousDefaultOutputDeviceID: AudioObjectID? = nil

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
        if let hp = self.outputDevices.first(where: { $0.name.lowercased().contains("headphone") || $0.name.contains("耳机") }) {
            self.selectedDevice = hp
        } else {
            self.selectedDevice = self.outputDevices.first { $0.isDefault } ?? self.outputDevices.first
        }
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
            let (srcFreqs, srcMags, usedSrc) = try await CSVFetcher.fetchCSVWithDetails(for: source)
            if usedSrc.provider.lowercased() != source.provider.lowercased() {
                appendLog("[i] Fallback provider for \(source.name): using \(usedSrc.provider) instead of \(source.provider)")
            }

            let (tgtFreqs, tgtMags, usedTgt) = try await CSVFetcher.fetchCSVWithDetails(for: target)
            if usedTgt.provider.lowercased() != target.provider.lowercased() {
                appendLog("[i] Fallback provider for \(target.name): using \(usedTgt.provider) instead of \(target.provider)")
            }

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
            appendLog("[!] 缺少拟合结果或未选择播放输出设备。")
            return
        }

        guard isBlackHoleFound, let blackHoleId = BlackHoleManager.getBlackHoleDeviceID() else {
            appendLog("[ERR] 未检测到 BlackHole 2ch 虚拟声卡。请先安装 BlackHole 驱动。")
            return
        }

        do {
            appendLog("[..] 正在生成 CamillaDSP 配置（目标输出: \(device.name))...")
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

            appendLog("[..] 正在启动 CamillaDSP 引擎...")
            try CamillaProcess.shared.start(configPath: configURL)

            // Save previous physical default output device and switch macOS system output to BlackHole 2ch
            let currentDef = CoreAudioService.getDefaultOutputDeviceID()
            if currentDef != blackHoleId {
                self.previousDefaultOutputDeviceID = currentDef
                CoreAudioService.setDefaultOutputDeviceID(blackHoleId)
                appendLog("[OK] 系统默认音频输出已自动路由至: BlackHole 2ch")
            } else if self.previousDefaultOutputDeviceID == nil {
                self.previousDefaultOutputDeviceID = device.id
            }

            self.isEngineRunning = true
            self.activePresetTitle = "\(selectedSource?.name ?? "") → \(selectedTarget?.name ?? "")"
            appendLog("[OK] CamillaDSP 已启动，声音由 BlackHole 采集滤波并输出至: \(device.name)")
            appendLog("[TIP] 若无声，请确认系统输出已选择 BlackHole 2ch，且输出设备为: \(device.name)")
        } catch {
            appendLog("[ERR] CamillaDSP 启动失败: \(error.localizedDescription)")
        }
    }

    public func stopCamillaDSP() {
        CamillaProcess.shared.stop()
        self.isEngineRunning = false
        self.activePresetTitle = nil

        // Automatically restore system output back to physical device
        if let prevId = previousDefaultOutputDeviceID {
            CoreAudioService.setDefaultOutputDeviceID(prevId)
            let prevName = CoreAudioService.getDeviceName(deviceID: prevId)
            appendLog("[i] 系统音频输出已恢复为: \(prevName)")
            self.previousDefaultOutputDeviceID = nil
        } else if let dev = selectedDevice {
            CoreAudioService.setDefaultOutputDeviceID(dev.id)
            appendLog("[i] 系统音频输出已恢复为: \(dev.name)")
        } else if let firstPhysical = outputDevices.first {
            CoreAudioService.setDefaultOutputDeviceID(firstPhysical.id)
            appendLog("[i] 系统音频输出已恢复为: \(firstPhysical.name)")
        }

        appendLog("[OK] CamillaDSP 已停止。")
    }

    public func refreshDevices() {
        self.outputDevices = CoreAudioService.getAudioOutputDevices()
        self.isBlackHoleFound = BlackHoleManager.isBlackHoleInstalled()

        if selectedDevice == nil || !outputDevices.contains(where: { $0.id == selectedDevice?.id }) {
            // Priority 1: Match the actual macOS default output device
            if let def = outputDevices.first(where: { $0.isDefault }) {
                self.selectedDevice = def
            } else if let prevId = previousDefaultOutputDeviceID, let prev = outputDevices.first(where: { $0.id == prevId }) {
                self.selectedDevice = prev
            } else if let spk = outputDevices.first(where: { $0.name.contains("扬声器") || $0.name.lowercased().contains("speaker") }) {
                self.selectedDevice = spk
            } else {
                self.selectedDevice = outputDevices.first
            }
        }
    }

    public func refreshPresets() {
        self.savedPresets = PresetsManager.listPresets()
    }

    public func loadPreset(_ preset: PresetInfo) {
        guard let device = selectedDevice else {
            appendLog("[!] 请选择播放输出设备。")
            return
        }
        appendLog("[..] 正在加载预设: \(preset.name)...")
        do {
            // Apply current selected playback device to preset YAML (matching original Python behavior)
            let activeConfigURL = try PresetsManager.preparePresetForLaunch(
                presetURL: preset.path,
                outputDeviceName: device.name
            )
            try CamillaProcess.shared.start(configPath: activeConfigURL)

            if let blackHoleId = BlackHoleManager.getBlackHoleDeviceID() {
                let currentDef = CoreAudioService.getDefaultOutputDeviceID()
                if currentDef != blackHoleId {
                    self.previousDefaultOutputDeviceID = currentDef
                    CoreAudioService.setDefaultOutputDeviceID(blackHoleId)
                    appendLog("[OK] 系统默认音频输出已自动路由至: BlackHole 2ch")
                } else if self.previousDefaultOutputDeviceID == nil {
                    self.previousDefaultOutputDeviceID = device.id
                }
            }

            self.isEngineRunning = true
            self.activePresetTitle = preset.name
            appendLog("[OK] 预设 \(preset.name) 已激活，音频输出至: \(device.name)")
            appendLog("[TIP] 若无声，请确认系统输出已选择 BlackHole 2ch，且输出设备为: \(device.name)")
        } catch {
            appendLog("[ERR] 加载预设 \(preset.name) 失败: \(error.localizedDescription)")
        }
    }

    public func reapplyCurrentPlaybackDevice() {
        guard isEngineRunning, let dev = selectedDevice else { return }
        appendLog("[..] 播放设备已更改为: \(dev.name)，正在重新定向引擎...")
        if let configURL = CamillaProcess.shared.activeConfigPath {
            do {
                let updatedURL = try PresetsManager.preparePresetForLaunch(
                    presetURL: configURL,
                    outputDeviceName: dev.name
                )
                try CamillaProcess.shared.start(configPath: updatedURL)
                appendLog("[OK] 引擎已成功重新定向至: \(dev.name)")
            } catch {
                appendLog("[ERR] 重新定向失败: \(error.localizedDescription)")
            }
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
