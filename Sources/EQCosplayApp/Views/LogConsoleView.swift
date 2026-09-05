import SwiftUI
import EQCosplayCore

public struct LogConsoleView: View {
    @ObservedObject var appState: AppState

    public init(appState: AppState) {
        self.appState = appState
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(I18n.shared.t("log_console"))
                    .font(.system(size: 11, weight: .medium, design: .monospaced))
                    .foregroundColor(.secondary)

                Spacer()

                Button(action: { appState.clearLogs() }) {
                    Text(I18n.shared.t("clear_log"))
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            }

            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 2) {
                        ForEach(Array(appState.logs.enumerated()), id: \.offset) { index, line in
                            Text(line)
                                .font(.system(size: 10, design: .monospaced))
                                .foregroundColor(colorForLine(line))
                                .textSelection(.enabled)
                                .id(index)
                        }
                    }
                    .padding(6)
                }
                .background(Color.black.opacity(0.2))
                .cornerRadius(6)
                .overlay(
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(Color.white.opacity(0.08), lineWidth: 0.5)
                )
                .onChange(of: appState.logs.count) { _ in
                    if let lastIndex = appState.logs.indices.last {
                        proxy.scrollTo(lastIndex, anchor: .bottom)
                    }
                }
            }
        }
        .padding(8)
        .background(.ultraThinMaterial)
        .cornerRadius(10)
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Color.white.opacity(0.12), lineWidth: 0.5)
        )
        .shadow(color: .black.opacity(0.05), radius: 4, x: 0, y: 1)
    }

    private func colorForLine(_ line: String) -> Color {
        if line.starts(with: "#") {
            return .secondary.opacity(0.6)
        } else if line.contains("[..]") {
            return .secondary
        }
        return .primary
    }
}
