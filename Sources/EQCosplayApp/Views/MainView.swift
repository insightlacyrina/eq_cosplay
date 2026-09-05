import SwiftUI
import EQCosplayCore

public struct MainView: View {
    @ObservedObject var appState: AppState
    @State private var currentLang: Language = I18n.shared.currentLanguage

    public init(appState: AppState) {
        self.appState = appState
    }

    public var body: some View {
        VStack(spacing: 12) {
            // Header Bar
            HStack(spacing: 12) {
                // Application Icon Alone
                if let icon = NSImage(contentsOfFile: "/Users/zhuyongfei/Desktop/eq_cosplay_swift/assets/icons/app.png") ?? NSImage(named: NSImage.applicationIconName) {
                    Image(nsImage: icon)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .frame(width: 28, height: 28)
                        .cornerRadius(6)
                        .overlay(
                            RoundedRectangle(cornerRadius: 6)
                                .stroke(Color.white.opacity(0.18), lineWidth: 0.5)
                        )
                        .shadow(color: .black.opacity(0.20), radius: 4, x: 0, y: 1)
                }

                Spacer()

                // Status indicator matched to selected language
                HStack(spacing: 7) {
                    Circle()
                        .fill(appState.isEngineRunning ? Color.primary : (appState.isCalculating ? Color.primary.opacity(0.7) : Color.secondary.opacity(0.35)))
                        .frame(width: 6, height: 6)

                    Text(appState.localizedStatus(for: currentLang))
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(appState.isEngineRunning ? .primary : .secondary)
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .liquidGlass(cornerRadius: 8)

                // Language Picker (Exact 105pt width, shared active coordinator)
                LiquidGlassDropdown(
                    id: "language",
                    items: Language.allCases,
                    selectedItem: Binding(
                        get: { currentLang },
                        set: { newLang in
                            currentLang = newLang
                            I18n.shared.currentLanguage = newLang
                        }
                    ),
                    activeDropdownId: $appState.activeDropdownId,
                    itemLabel: { $0.label },
                    width: 105
                )
            }
            .padding(.horizontal, 4)
            .zIndex(100)

            // Step 1: Headphone Selection (Morphing Liquid Glass with Floating Layer)
            HeadphonePickerView(appState: appState)
                .zIndex(90)

            // Step 2: Settings & Actions (Morphing Liquid Glass with Floating Layer)
            SettingsBarView(appState: appState)
                .zIndex(80)

            // Step 3: Main Display (Frequency Plot + PEQ Table - Dynamically Resizes With Window)
            HStack(alignment: .top, spacing: 12) {
                FrequencyResponsePlotView(appState: appState)
                    .frame(minWidth: 540)
                    .frame(maxHeight: .infinity)

                PEQTableView(appState: appState)
                    .frame(width: 320)
                    .frame(maxHeight: .infinity)
            }
            .frame(minHeight: 220, maxHeight: .infinity)

            // Step 4: Bottom Row (Presets Library + Live Logs - Stable Anchor)
            HStack(spacing: 12) {
                PresetSidebarView(appState: appState)
                    .frame(width: 280)
                    .frame(height: 150)

                LogConsoleView(appState: appState)
                    .frame(minWidth: 400)
                    .frame(height: 150)
            }
        }
        .padding(14)
        .background(Color.black)
        .contentShape(Rectangle())
        .onTapGesture {
            if appState.activeDropdownId != nil {
                withAnimation(.spring(response: 0.28, dampingFraction: 0.78)) {
                    appState.activeDropdownId = nil
                }
            }
        }
        .preferredColorScheme(.dark)
        .task {
            await appState.initialLoad()
        }
    }
}
