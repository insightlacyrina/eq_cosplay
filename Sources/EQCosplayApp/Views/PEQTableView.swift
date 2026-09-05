import SwiftUI
import EQCosplayCore

public struct PEQTableView: View {
    @ObservedObject var appState: AppState

    public init(appState: AppState) {
        self.appState = appState
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            // Header with metrics
            HStack {
                Text(I18n.shared.t("peq_table_title"))
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(.primary)

                Spacer()

                if let res = appState.correctionResult {
                    HStack(spacing: 6) {
                        metricPill(
                            label: "IIR RMSE",
                            value: String(format: "%.2f dB", res.peqRmse)
                        )
                        if res.useFir {
                            metricPill(
                                label: "FIR RMSE",
                                value: String(format: "%.2f dB", res.combinedRmse)
                            )
                            metricPill(
                                label: "FIR",
                                value: "\(res.firTaps) Taps"
                            )
                        }
                    }
                }
            }

            // Table Box (Fills maxHeight to strictly match FrequencyResponsePlotView)
            VStack(spacing: 0) {
                // Table Header
                HStack {
                    Text(I18n.shared.t("col_index"))
                        .frame(width: 32, alignment: .leading)
                    Text(I18n.shared.t("col_type"))
                        .frame(width: 90, alignment: .leading)
                    Text(I18n.shared.t("col_freq"))
                        .frame(maxWidth: .infinity, alignment: .trailing)
                    Text(I18n.shared.t("col_gain"))
                        .frame(maxWidth: .infinity, alignment: .trailing)
                    Text(I18n.shared.t("col_q"))
                        .frame(maxWidth: .infinity, alignment: .trailing)
                }
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(.secondary)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(.ultraThinMaterial)

                Divider().background(Color.white.opacity(0.08))

                // Table Rows / Empty State
                if let bands = appState.correctionResult?.peqBands, !bands.isEmpty {
                    ScrollView {
                        VStack(spacing: 0) {
                            ForEach(Array(bands.enumerated()), id: \.offset) { index, band in
                                HStack {
                                    Text(String(format: "%02d", index + 1))
                                        .font(.system(size: 11, design: .monospaced))
                                        .foregroundColor(.secondary)
                                        .frame(width: 32, alignment: .leading)

                                    typeBadge(band.type)
                                        .frame(width: 90, alignment: .leading)

                                    Text(String(format: "%.1f Hz", band.frequency))
                                        .font(.system(size: 11, design: .monospaced))
                                        .foregroundColor(.primary)
                                        .frame(maxWidth: .infinity, alignment: .trailing)

                                    Text(String(format: "%+.2f dB", band.gain))
                                        .font(.system(size: 11, weight: .medium, design: .monospaced))
                                        .foregroundColor(.primary)
                                        .frame(maxWidth: .infinity, alignment: .trailing)

                                    Text(String(format: "%.2f", band.q))
                                        .font(.system(size: 11, design: .monospaced))
                                        .foregroundColor(.secondary)
                                        .frame(maxWidth: .infinity, alignment: .trailing)
                                }
                                .padding(.horizontal, 10)
                                .padding(.vertical, 5)
                                .background(index % 2 == 0 ? Color.clear : Color.primary.opacity(0.03))

                                if index < bands.count - 1 {
                                    Divider().background(Color.white.opacity(0.04))
                                }
                            }
                        }
                    }
                    .frame(maxHeight: .infinity)
                } else {
                    VStack {
                        Spacer()
                        Text("尚未生成均衡器参数")
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                        Spacer()
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .frame(maxHeight: .infinity)
            .background(.ultraThinMaterial)
            .cornerRadius(8)
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(Color.white.opacity(0.1), lineWidth: 0.5)
            )
        }
        .padding(12)
        .frame(maxHeight: .infinity)
        .liquidGlass(cornerRadius: 10)
    }

    private func metricPill(label: String, value: String) -> some View {
        HStack(spacing: 4) {
            Text(label)
                .font(.system(size: 10))
                .foregroundColor(.secondary)
            Text(value)
                .font(.system(size: 10, weight: .medium, design: .monospaced))
                .foregroundColor(.primary)
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 2)
        .background(.ultraThinMaterial)
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.white.opacity(0.1), lineWidth: 0.5)
        )
    }

    private func typeBadge(_ type: FilterType) -> some View {
        Text(type.displayName)
            .font(.system(size: 9, weight: .medium))
            .foregroundColor(.secondary)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(.ultraThinMaterial)
            .cornerRadius(4)
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color.white.opacity(0.1), lineWidth: 0.5)
            )
    }
}
