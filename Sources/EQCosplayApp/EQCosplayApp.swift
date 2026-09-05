import SwiftUI
import AppKit
import EQCosplayCore

class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        // Keep running in menu bar when window is closed, matching original app
        return false
    }

    func applicationWillTerminate(_ notification: Notification) {
        CamillaProcess.shared.stop()
    }
}

@main
struct EQCosplaySwiftApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var appState = AppState()

    var body: some Scene {
        Window("EQ Cosplay", id: "main_window") {
            MainView(appState: appState)
                .frame(minWidth: 940, minHeight: 680)
                .ignoresSafeArea(.all, edges: .top)
        }
        .windowStyle(.hiddenTitleBar)

        MenuBarExtra {
            VStack {
                Text(appState.isEngineRunning ? (appState.activePresetTitle ?? "CamillaDSP Running") : I18n.shared.t("status_idle"))
                    .font(.caption)
                    .foregroundColor(appState.isEngineRunning ? .green : .secondary)

                Divider()

                Text(I18n.shared.t("presets_library"))
                    .font(.caption.bold())

                if appState.savedPresets.isEmpty {
                    Text(I18n.shared.t("no_presets"))
                        .font(.caption)
                        .foregroundColor(.secondary)
                } else {
                    ForEach(appState.savedPresets.prefix(12)) { preset in
                        Button(action: {
                            appState.loadPreset(preset)
                        }) {
                            HStack {
                                if appState.activePresetTitle == preset.name {
                                    Image(systemName: "checkmark")
                                }
                                Text(preset.name)
                            }
                        }
                    }
                }

                Divider()

                Button(I18n.shared.t("menubar_show")) {
                    NSApp.activate(ignoringOtherApps: true)
                    for window in NSApp.windows {
                        if window.canBecomeMain {
                            window.makeKeyAndOrderFront(nil)
                        }
                    }
                }

                if appState.isEngineRunning {
                    if appState.hasFIRData {
                        Button(appState.isFIREnabled ? I18n.shared.t("fir_stop") : I18n.shared.t("fir_enable")) {
                            appState.toggleFIR()
                        }
                    }

                    Button(I18n.shared.t("menubar_stop")) {
                        appState.stopCamillaDSP()
                    }
                }

                Button(I18n.shared.t("menubar_refresh")) {
                    appState.refreshPresets()
                }

                Divider()

                Button(I18n.shared.t("menubar_quit")) {
                    CamillaProcess.shared.stop()
                    NSApp.terminate(nil)
                }
            }
        } label: {
            HStack(spacing: 2) {
                Image(systemName: appState.isEngineRunning ? "waveform.badge.magnifyingglass" : "waveform")
                Text(appState.isEngineRunning ? "EQ" : "EQ")
            }
        }
    }
}
