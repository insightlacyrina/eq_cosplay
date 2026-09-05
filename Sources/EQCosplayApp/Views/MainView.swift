import SwiftUI
import EQCosplayCore

// MARK: - Native macOS Window Drag Support
public struct WindowDragArea: NSViewRepresentable {
    public final class DragView: NSView {
        public override var mouseDownCanMoveWindow: Bool { true }

        public override func mouseUp(with event: NSEvent) {
            if event.clickCount == 2 {
                window?.zoom(nil)
            } else {
                super.mouseUp(with: event)
            }
        }
    }

    public init() {}

    public func makeNSView(context: Context) -> DragView {
        return DragView()
    }

    public func updateNSView(_ nsView: DragView, context: Context) {}
}

extension View {
    @ViewBuilder
    public func enableWindowDrag() -> some View {
        if #available(macOS 15.0, *) {
            self.gesture(WindowDragGesture())
        } else {
            self
        }
    }
}

public struct MainView: View {
    @ObservedObject var appState: AppState
    @State private var currentLang: Language = I18n.shared.currentLanguage

    public init(appState: AppState) {
        self.appState = appState
    }

    public var body: some View {
        VStack(spacing: 8) {
            // Header Bar / Custom Top Bar (Unified with macOS Window Traffic Light Controls)
            HStack(spacing: 12) {
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
            .padding(.leading, 80) // Reserved margin for traffic lights (close, minimize, zoom)
            .padding(.trailing, 14)
            .padding(.top, 10)
            .padding(.bottom, 2)
            .frame(height: 44)
            .background(
                WindowDragArea()
                    .enableWindowDrag()
            )
            .enableWindowDrag()
            .zIndex(100)

            // Main Content Area
            VStack(spacing: 12) {
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
                        .frame(width: 385)
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
            .padding(.horizontal, 14)
            .padding(.bottom, 14)
        }
        .background(Color.black)
        .ignoresSafeArea(.all, edges: .top)
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
