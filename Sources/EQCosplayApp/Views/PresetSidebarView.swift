import SwiftUI
import EQCosplayCore

public struct PresetSidebarView: View {
    @ObservedObject var appState: AppState

    public init(appState: AppState) {
        self.appState = appState
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            header
            content
        }
        .padding(10)
        .background(
            ZStack {
                RoundedRectangle(cornerRadius: 10)
                    .fill(.ultraThinMaterial)
                RoundedRectangle(cornerRadius: 10)
                    .fill(Color.black.opacity(0.3))
            }
        )
        .cornerRadius(10)
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Color.white.opacity(0.12), lineWidth: 0.5)
        )
        .shadow(color: .black.opacity(0.05), radius: 4, x: 0, y: 1)
    }

    private var header: some View {
        HStack {
            Text(I18n.shared.t("presets_library"))
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(.primary)
            Spacer()
            Button(action: { appState.refreshPresets() }) {
                Image(systemName: "arrow.clockwise")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
        }
    }

    @ViewBuilder
    private var content: some View {
        if appState.savedPresets.isEmpty {
            VStack {
                Spacer()
                Text(I18n.shared.t("no_presets"))
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                Spacer()
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            ScrollView {
                VStack(spacing: 4) {
                    ForEach(appState.savedPresets) { preset in
                        presetRow(preset)
                    }
                }
            }
        }
    }

    private func presetRow(_ preset: PresetInfo) -> some View {
        let isCurrent = appState.activePresetTitle == preset.name
        let peqRmse = preset.metrics["peq_rmse"]

        return HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(preset.name)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(.primary)
                    .lineLimit(1)

                HStack(spacing: 6) {
                    if preset.hasFir {
                        Text("FIR")
                            .font(.system(size: 9, weight: .medium))
                            .foregroundColor(.secondary)
                            .padding(.horizontal, 4)
                            .background(.ultraThinMaterial)
                            .cornerRadius(3)
                            .overlay(
                                RoundedRectangle(cornerRadius: 3)
                                    .stroke(Color.white.opacity(0.1), lineWidth: 0.5)
                            )
                    }
                    if let rmse = peqRmse {
                        Text(String(format: "%.2fdB", rmse))
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundColor(.secondary)
                    }
                }
            }

            Spacer()

            Button(action: {
                appState.loadPreset(preset)
            }) {
                Image(systemName: "play.circle")
                    .font(.system(size: 15))
                    .foregroundColor(.primary)
            }
            .buttonStyle(.plain)

            Button(action: {
                PresetsManager.deletePreset(preset)
                appState.refreshPresets()
            }) {
                Image(systemName: "trash")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
        }
        .padding(6)
        .background(isCurrent ? Color.primary.opacity(0.12) : Color.white.opacity(0.04))
        .cornerRadius(6)
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(Color.white.opacity(0.08), lineWidth: 0.5)
        )
    }
}
