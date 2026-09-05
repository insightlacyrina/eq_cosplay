import SwiftUI
import EQCosplayCore

struct PreampOption: Identifiable, Equatable {
    let id: String
    let mode: PreampMode
    let label: String
}

public struct SettingsBarView: View {
    @ObservedObject var appState: AppState

    public init(appState: AppState) {
        self.appState = appState
    }

    private var preampOptions: [PreampOption] {
        [
            PreampOption(id: I18n.shared.t("preamp_safe"), mode: .safe, label: I18n.shared.t("preamp_safe")),
            PreampOption(id: I18n.shared.t("preamp_moderate"), mode: .moderate, label: I18n.shared.t("preamp_moderate")),
            PreampOption(id: I18n.shared.t("preamp_custom"), mode: .custom(appState.customPreamp), label: I18n.shared.t("preamp_custom")),
            PreampOption(id: I18n.shared.t("preamp_none"), mode: .none, label: I18n.shared.t("preamp_none"))
        ]
    }

    private var selectedPreampOption: Binding<PreampOption> {
        Binding(
            get: {
                let currentLabel: String
                switch appState.preampMode {
                case .safe: currentLabel = I18n.shared.t("preamp_safe")
                case .moderate: currentLabel = I18n.shared.t("preamp_moderate")
                case .custom: currentLabel = I18n.shared.t("preamp_custom")
                case .none: currentLabel = I18n.shared.t("preamp_none")
                }
                return PreampOption(id: currentLabel, mode: appState.preampMode, label: currentLabel)
            },
            set: { newOption in
                appState.preampMode = newOption.mode
            }
        )
    }

    private var selectedDeviceBinding: Binding<AudioDevice> {
        Binding(
            get: {
                appState.selectedDevice ?? appState.outputDevices.first ?? AudioDevice(id: 0, name: "Output", uid: "default", isDefault: true)
            },
            set: { newDev in
                appState.selectedDevice = newDev
                appState.reapplyCurrentPlaybackDevice()
            }
        )
    }

    public var body: some View {
        VStack(spacing: 10) {
            HStack(alignment: .center, spacing: 14) {
                // Preamp Mode (Liquid Glass Morphing Dropdown with Shared Coordinator)
                VStack(alignment: .leading, spacing: 4) {
                    Text(I18n.shared.t("preamp_label"))
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(.secondary)

                    LiquidGlassDropdown(
                        id: "preamp",
                        items: preampOptions,
                        selectedItem: selectedPreampOption,
                        activeDropdownId: $appState.activeDropdownId,
                        itemLabel: { $0.label },
                        width: 175
                    )
                }

                // Sample Rate (Liquid Glass Morphing Dropdown with Shared Coordinator)
                VStack(alignment: .leading, spacing: 4) {
                    Text(I18n.shared.t("sample_rate"))
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(.secondary)

                    LiquidGlassDropdown(
                        id: "sample_rate",
                        items: SupportedSampleRate.allCases,
                        selectedItem: $appState.sampleRate,
                        activeDropdownId: $appState.activeDropdownId,
                        itemLabel: { $0.label },
                        width: 115
                    )
                }

                // Output Audio Device (Liquid Glass Morphing Dropdown with Shared Coordinator)
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 4) {
                        Text(I18n.shared.t("output_device"))
                            .font(.system(size: 11, weight: .medium))
                            .foregroundColor(.secondary)

                        Button(action: { appState.refreshDevices() }) {
                            Image(systemName: "arrow.triangle.2.circlepath")
                                .font(.system(size: 10))
                                .foregroundColor(.secondary)
                        }
                        .buttonStyle(.plain)
                    }

                    LiquidGlassDropdown(
                        id: "output_device",
                        items: appState.outputDevices.isEmpty ? [AudioDevice(id: 0, name: "Default Output", uid: "default", isDefault: true)] : appState.outputDevices,
                        selectedItem: selectedDeviceBinding,
                        activeDropdownId: $appState.activeDropdownId,
                        itemLabel: { $0.name },
                        width: 180
                    )
                }

                Spacer()

                // Action Buttons (High disabled contrast & Liquid Glass effect)
                HStack(spacing: 10) {
                    // Toggle FIR Button (Displayed only when FIR data is present, placed to the left of calculate button)
                    if appState.hasFIRData {
                        LiquidGlassButton(
                            title: I18n.shared.t(appState.isFIREnabled ? "fir_stop" : "fir_enable"),
                            icon: appState.isFIREnabled ? "waveform.badge.minus" : "waveform.badge.plus",
                            isLoading: false,
                            isProminent: false,
                            isDisabled: appState.isCalculating,
                            action: {
                                appState.toggleFIR()
                            }
                        )
                    }

                    // Compute / Optimize Button
                    LiquidGlassButton(
                        title: I18n.shared.t("calculate_button"),
                        icon: appState.isCalculating ? nil : "waveform.path.ecg",
                        isLoading: appState.isCalculating,
                        isProminent: false,
                        isDisabled: appState.isCalculating || appState.selectedSource == nil || appState.selectedTarget == nil,
                        action: {
                            Task { await appState.calculateCorrection() }
                        }
                    )

                    // Start DSP Button
                    LiquidGlassButton(
                        title: I18n.shared.t("deploy_button"),
                        icon: "play.fill",
                        isProminent: true,
                        isDisabled: appState.correctionResult == nil,
                        action: {
                            appState.deployCamillaDSP()
                        }
                    )

                    // Stop DSP Button
                    if appState.isEngineRunning {
                        LiquidGlassButton(
                            title: I18n.shared.t("stop_button"),
                            icon: "stop.fill",
                            isProminent: false,
                            isDisabled: false,
                            action: {
                                appState.stopCamillaDSP()
                            }
                        )
                    }
                }
            }

            // BlackHole Warning & Automated Installation (Liquid Glass)
            if !appState.isBlackHoleFound {
                HStack(spacing: 10) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 13))
                        .foregroundColor(Color.orange.opacity(0.85))

                    Text(I18n.shared.t("blackhole_warning"))
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)

                    Spacer()

                    LiquidGlassButton(
                        title: I18n.shared.t(appState.isInstallingBlackHole ? "installing_blackhole" : "install_blackhole"),
                        icon: appState.isInstallingBlackHole ? nil : "arrow.down.circle",
                        isLoading: appState.isInstallingBlackHole,
                        isProminent: true,
                        isDisabled: appState.isInstallingBlackHole,
                        action: {
                            appState.installBlackHole()
                        }
                    )
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .liquidGlass(cornerRadius: 8)
            }
        }
        .padding(12)
        .liquidGlass(cornerRadius: 10)
    }
}
