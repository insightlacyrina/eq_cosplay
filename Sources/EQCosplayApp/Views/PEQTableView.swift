import SwiftUI
import EQCosplayCore

public struct PEQTableView: View {
    @ObservedObject var appState: AppState

    public init(appState: AppState) {
        self.appState = appState
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            // Header with metrics (no boxes, 3 leading-aligned horizontal rows)
            HStack(alignment: .top) {
                Text(I18n.shared.t("peq_table_title"))
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(.primary)

                Spacer()

                if let res = appState.correctionResult {
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 5) {
                            Text("IIR RMSE:")
                                .font(.system(size: 10))
                                .foregroundColor(.secondary)
                            Text(String(format: "%.2f dB", res.peqRmse))
                                .font(.system(size: 10, weight: .medium, design: .monospaced))
                                .foregroundColor(.primary)
                        }

                        HStack(spacing: 5) {
                            Text("FIR RMSE:")
                                .font(.system(size: 10))
                                .foregroundColor(.secondary)
                            Text(res.useFir ? String(format: "%.2f dB", res.combinedRmse) : "—")
                                .font(.system(size: 10, weight: .medium, design: .monospaced))
                                .foregroundColor(.primary)
                        }

                        HStack(spacing: 5) {
                            Text("FIR Taps:")
                                .font(.system(size: 10))
                                .foregroundColor(.secondary)
                            Text(res.useFir ? "\(res.firTaps)" : "—")
                                .font(.system(size: 10, weight: .medium, design: .monospaced))
                                .foregroundColor(.primary)
                        }
                    }
                }
            }

            // Table Box (Fills maxHeight to strictly match FrequencyResponsePlotView)
            VStack(spacing: 0) {
                // Table Header with Units in Parentheses
                HStack(spacing: 6) {
                    Text(I18n.shared.t("col_index"))
                        .frame(width: 26, alignment: .leading)
                    Text(I18n.shared.t("col_type"))
                        .frame(width: 62, alignment: .leading)
                    Text(I18n.shared.t("col_freq"))
                        .frame(maxWidth: .infinity, alignment: .trailing)
                    Text(I18n.shared.t("col_gain"))
                        .frame(width: 64, alignment: .trailing)
                    Text(I18n.shared.t("col_q"))
                        .frame(width: 54, alignment: .trailing)
                }
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(.secondary)
                .lineLimit(1)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(Color.black.opacity(0.25))

                Divider().background(Color.white.opacity(0.08))

                // Table Rows / Empty State
                if let bands = appState.correctionResult?.peqBands, !bands.isEmpty {
                    ScrollView {
                        VStack(spacing: 0) {
                            ForEach(Array(bands.enumerated()), id: \.offset) { index, band in
                                HStack(spacing: 6) {
                                    Text(String(format: "%02d", index + 1))
                                        .font(.system(size: 11, design: .monospaced))
                                        .foregroundColor(.secondary)
                                        .frame(width: 26, alignment: .leading)

                                    typeBadge(band.type)
                                        .frame(width: 62, alignment: .leading)

                                    Text(band.frequency >= 100 ? String(format: "%.0f", band.frequency) : String(format: "%.1f", band.frequency))
                                        .font(.system(size: 11, design: .monospaced))
                                        .foregroundColor(.primary)
                                        .frame(maxWidth: .infinity, alignment: .trailing)

                                    Text(String(format: "%+.2f", band.gain))
                                        .font(.system(size: 11, weight: .medium, design: .monospaced))
                                        .foregroundColor(.primary)
                                        .frame(width: 64, alignment: .trailing)

                                    Text(String(format: "%.2f", band.q))
                                        .font(.system(size: 11, design: .monospaced))
                                        .foregroundColor(.secondary)
                                        .frame(width: 54, alignment: .trailing)
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
            .background(Color.black.opacity(0.2))
            .cornerRadius(8)
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(Color.white.opacity(0.08), lineWidth: 0.5)
            )
        }
        .padding(10)
        .frame(maxHeight: .infinity)
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
