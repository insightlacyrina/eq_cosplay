import SwiftUI
import AppKit
import EQCosplayCore

public struct PresetSidebarView: View {
    @ObservedObject var appState: AppState
    @State private var hoveredPresetId: String? = nil
    @State private var rowPositions: [String: CGFloat] = [:]

    public init(appState: AppState) {
        self.appState = appState
    }

    public var body: some View {
        // Fixed layout anchor: strictly 280x150 so local preset library module size NEVER shifts
        Color.clear
            .frame(width: 280, height: 150)
            .overlay(alignment: .topLeading) {
                mainLibraryCard
            }
            .overlay(alignment: .topLeading) {
                if let expId = appState.activeExpandedPresetId,
                   let preset = appState.savedPresets.first(where: { $0.id == expId }) {
                    ExpandedPresetCardView(
                        preset: preset,
                        isCurrent: appState.activePresetTitle == preset.name,
                        targetWidth: calculateExpandedWidth(for: preset.name),
                        appState: appState,
                        onCollapse: {
                            appState.activeExpandedPresetId = nil
                        }
                    )
                    .id(preset.id)
                    .offset(x: 10, y: max(32, min(rowPositions[expId] ?? 36, 104)))
                    .zIndex(999)
                }
            }
            .coordinateSpace(name: "PresetSidebarSpace")
    }

    private var mainLibraryCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            header
            content
        }
        .padding(10)
        .frame(width: 280, height: 150, alignment: .topLeading)
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
        .onPreferenceChange(PresetRowPositionPreferenceKey.self) { prefs in
            for (k, v) in prefs {
                rowPositions[k] = v
            }
        }
    }

    private var header: some View {
        HStack {
            Text(I18n.shared.t("presets_library"))
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(.primary)
            Spacer()
            Button(action: {
                withAnimation(.spring(response: 0.28, dampingFraction: 0.78)) {
                    appState.activeExpandedPresetId = nil
                }
                appState.refreshPresets()
            }) {
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
            ScrollView(.vertical, showsIndicators: true) {
                VStack(spacing: 5) {
                    ForEach(appState.savedPresets) { preset in
                        presetRow(preset)
                    }
                }
                .padding(.vertical, 2)
            }
        }
    }

    private func presetRow(_ preset: PresetInfo) -> some View {
        let isCurrent = appState.activePresetTitle == preset.name
        let isHovered = hoveredPresetId == preset.id
        let peqRmse = preset.metrics["peq_rmse"]

        return GeometryReader { geo in
            HStack(spacing: 6) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(preset.name)
                        .font(.system(size: 11, weight: isCurrent ? .semibold : .medium))
                        .foregroundColor(isCurrent ? .primary : Color.white.opacity(0.85))
                        .lineLimit(1)

                    HStack(spacing: 5) {
                        if preset.hasFir {
                            Text("FIR")
                                .font(.system(size: 8, weight: .bold))
                                .foregroundColor(.primary)
                                .padding(.horizontal, 3)
                                .padding(.vertical, 1)
                                .background(Color.white.opacity(0.12))
                                .cornerRadius(3)
                        }
                        if let rmse = peqRmse {
                            Text(String(format: "%.2f dB", rmse))
                                .font(.system(size: 9, design: .monospaced))
                                .foregroundColor(.secondary)
                        }
                    }
                }

                Spacer(minLength: 4)

                // Quick Play Button (Circular)
                Button(action: {
                    appState.loadPreset(preset)
                }) {
                    Image(systemName: isCurrent ? "waveform" : "play.fill")
                        .font(.system(size: 10))
                        .foregroundColor(isCurrent ? .primary : .secondary)
                        .frame(width: 20, height: 20)
                        .background(isCurrent ? Color.white.opacity(0.2) : Color.white.opacity(0.06))
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)

                // Quick Delete Button (Circular)
                Button(action: {
                    withAnimation(.spring(response: 0.28, dampingFraction: 0.78)) {
                        if appState.activeExpandedPresetId == preset.id {
                            appState.activeExpandedPresetId = nil
                        }
                    }
                    PresetsManager.deletePreset(preset)
                    appState.refreshPresets()
                }) {
                    Image(systemName: "trash")
                        .font(.system(size: 9))
                        .foregroundColor(.secondary.opacity(0.7))
                        .frame(width: 18, height: 18)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .frame(width: 260, height: 36, alignment: .leading)
            .background(
                ZStack {
                    RoundedRectangle(cornerRadius: 8)
                        .fill(isCurrent ? Color.white.opacity(0.14) : Color.white.opacity(isHovered ? 0.08 : 0.03))

                    RoundedRectangle(cornerRadius: 8)
                        .strokeBorder(
                            LinearGradient(
                                stops: [
                                    .init(color: .white.opacity(isHovered ? 0.40 : 0.18), location: 0.0),
                                    .init(color: .white.opacity(isHovered ? 0.15 : 0.05), location: 0.5),
                                    .init(color: .clear, location: 1.0)
                                ],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            ),
                            lineWidth: 0.75
                        )
                }
            )
            .liquidGlass(cornerRadius: 8, isInteractive: true, isHighlighted: isHovered || isCurrent)
            .brightness(isHovered ? 0.06 : 0.0)
            .contentShape(Rectangle())
            .onHover { h in
                hoveredPresetId = h ? preset.id : nil
            }
            .onTapGesture {
                if appState.activeExpandedPresetId == preset.id {
                    withAnimation(.spring(response: 0.28, dampingFraction: 0.80)) {
                        appState.activeExpandedPresetId = nil
                    }
                } else if appState.activeExpandedPresetId != nil {
                    // Smoothly transition from previous tab to new tab
                    withAnimation(.spring(response: 0.20, dampingFraction: 0.85)) {
                        appState.activeExpandedPresetId = nil
                    }
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.16) {
                        withAnimation(.spring(response: 0.32, dampingFraction: 0.76)) {
                            appState.activeExpandedPresetId = preset.id
                        }
                    }
                } else {
                    withAnimation(.spring(response: 0.32, dampingFraction: 0.76)) {
                        appState.activeExpandedPresetId = preset.id
                    }
                }
            }
            .preference(
                key: PresetRowPositionPreferenceKey.self,
                value: [preset.id: geo.frame(in: .named("PresetSidebarSpace")).minY]
            )
        }
        .frame(height: 36)
    }

    // Flexible width calculation based on font measurements
    private func calculateExpandedWidth(for presetName: String) -> CGFloat {
        let font = NSFont.systemFont(ofSize: 11, weight: .semibold)
        let attrString = NSAttributedString(string: presetName, attributes: [.font: font])
        let textWidth = ceil(attrString.size().width)
        // textWidth + spacing + action buttons (~60pt) + padding (~24pt)
        let needed = textWidth + 88.0
        // Flexible width clamped from 480pt up to 680pt
        return min(max(needed, 480.0), 680.0)
    }
}

// MARK: - Horizontally Morphing Liquid Glass Card
private struct ExpandedPresetCardView: View {
    let preset: PresetInfo
    let isCurrent: Bool
    let targetWidth: CGFloat
    @ObservedObject var appState: AppState
    let onCollapse: () -> Void

    @State private var currentWidth: CGFloat = 260

    var body: some View {
        let peqRmse = preset.metrics["peq_rmse"]
        let combinedRmse = preset.metrics["combined_rmse"]

        ZStack(alignment: .leading) {
            // Ambient Blur Halo (expands rightward strictly with .leading anchor)
            RoundedRectangle(cornerRadius: 8)
                .fill(.ultraThinMaterial)
                .frame(width: currentWidth + 6, height: 38, alignment: .leading)
                .blur(radius: 6)
                .shadow(color: .black.opacity(0.40), radius: 16, x: 2, y: 5)
                .offset(x: -3, y: -1)

            // The Liquid Glass Card: identical brightness & highlights to hovered tab
            HStack(spacing: 8) {
                // Headphone name (starts at exact same left padding as collapsed row, no circle icon)
                VStack(alignment: .leading, spacing: 2) {
                    Text(preset.name)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(.primary)
                        .lineLimit(1)

                    HStack(spacing: 6) {
                        if preset.hasFir {
                            HStack(spacing: 3) {
                                Circle().fill(Color.primary).frame(width: 3.5, height: 3.5)
                                Text("FIR (1024)")
                                    .font(.system(size: 8, weight: .bold))
                                    .foregroundColor(.primary)
                            }
                            .padding(.horizontal, 4)
                            .padding(.vertical, 1)
                            .background(Color.white.opacity(0.14))
                            .cornerRadius(3)
                        }

                        if let rmse = peqRmse {
                            Text(String(format: "PEQ: %.2f dB", rmse))
                                .font(.system(size: 9, design: .monospaced))
                                .foregroundColor(.secondary)
                        }

                        if let comb = combinedRmse, preset.hasFir, abs(comb - (peqRmse ?? 0)) > 1e-4 {
                            Text(String(format: "Comb: %.2f dB", comb))
                                .font(.system(size: 9, design: .monospaced))
                                .foregroundColor(.secondary)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                // Actions: Keeps original circular buttons, NO text capsule, NO extra "x" button
                HStack(spacing: 6) {
                    // Quick Load / Activate Button (Identical Circular shape & size)
                    Button(action: {
                        appState.loadPreset(preset)
                        collapse()
                    }) {
                        Image(systemName: isCurrent ? "waveform" : "play.fill")
                            .font(.system(size: 10))
                            .foregroundColor(isCurrent ? .primary : .secondary)
                            .frame(width: 20, height: 20)
                            .background(isCurrent ? Color.white.opacity(0.2) : Color.white.opacity(0.08))
                            .clipShape(Circle())
                    }
                    .buttonStyle(.plain)

                    // Delete Button (Circular)
                    Button(action: {
                        collapse()
                        PresetsManager.deletePreset(preset)
                        appState.refreshPresets()
                    }) {
                        Image(systemName: "trash")
                            .font(.system(size: 9))
                            .foregroundColor(.secondary.opacity(0.75))
                            .frame(width: 20, height: 20)
                            .background(Color.white.opacity(0.06))
                            .clipShape(Circle())
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .frame(width: currentWidth, height: 36, alignment: .leading)
            .background(
                ZStack {
                    RoundedRectangle(cornerRadius: 8)
                        .fill(isCurrent ? Color.white.opacity(0.14) : Color.white.opacity(0.08))

                    RoundedRectangle(cornerRadius: 8)
                        .strokeBorder(
                            LinearGradient(
                                stops: [
                                    .init(color: .white.opacity(0.40), location: 0.0),
                                    .init(color: .white.opacity(0.15), location: 0.5),
                                    .init(color: .clear, location: 1.0)
                                ],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            ),
                            lineWidth: 0.75
                        )
                }
            )
            .liquidGlass(cornerRadius: 8, isInteractive: true, isHighlighted: true)
            .brightness(0.06)
        }
        .frame(width: currentWidth, height: 36, alignment: .leading)
        .contentShape(Rectangle())
        .onTapGesture {
            collapse()
        }
        .onAppear {
            // Anchor left edge firmly at x:0, smoothly expand only the right edge outward
            withAnimation(.spring(response: 0.32, dampingFraction: 0.76)) {
                currentWidth = targetWidth
            }
        }
    }

    private func collapse() {
        withAnimation(.spring(response: 0.28, dampingFraction: 0.80)) {
            currentWidth = 260
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.26) {
            onCollapse()
        }
    }
}

private struct PresetRowPositionPreferenceKey: PreferenceKey {
    static var defaultValue: [String: CGFloat] = [:]
    static func reduce(value: inout [String: CGFloat], nextValue: () -> [String: CGFloat]) {
        value.merge(nextValue()) { $1 }
    }
}
