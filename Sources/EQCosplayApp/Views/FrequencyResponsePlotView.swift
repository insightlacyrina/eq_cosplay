import SwiftUI
import EQCosplayCore

public struct FrequencyResponsePlotView: View {
    @ObservedObject var appState: AppState
    @State private var hoverLocation: CGPoint? = nil
    @State private var hoverFreq: Double? = nil

    private let fMin = 20.0
    private let fMax = 20000.0
    private let logMin = log10(20.0)
    private let logMax = log10(20000.0)

    public init(appState: AppState) {
        self.appState = appState
    }

    public var body: some View {
        VStack(spacing: 8) {
            // Plot Header & Legend (All monochrome text)
            HStack(spacing: 16) {
                legendItem(title: I18n.shared.t("plot_source"), color: Color(white: 0.6))
                legendItem(title: I18n.shared.t("plot_target"), color: Color.white)
                legendItem(title: I18n.shared.t("plot_simulated"), color: Color(red: 0.35, green: 0.85, blue: 0.75))

                Spacer()

                if let f = hoverFreq {
                    Text(String(format: "%.0f Hz", f))
                        .font(.system(size: 11, weight: .medium, design: .monospaced))
                        .foregroundColor(.primary)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(.ultraThinMaterial)
                        .cornerRadius(6)
                        .overlay(
                            RoundedRectangle(cornerRadius: 6)
                                .stroke(Color.white.opacity(0.15), lineWidth: 0.5)
                        )
                }
            }
            .padding(.horizontal, 8)

            // Plot Canvas
            GeometryReader { geo in
                let w = geo.size.width
                let h = geo.size.height
                let padL: CGFloat = 42
                let padR: CGFloat = 16
                let padT: CGFloat = 12
                let padB: CGFloat = 26
                let plotW = max(w - padL - padR, 10)
                let plotH = max(h - padT - padB, 10)

                let bounds = computeYBounds()
                let yMin = bounds.min
                let yMax = bounds.max

                ZStack(alignment: .topLeading) {
                    Canvas { ctx, size in
                        // Background rect (Subtle transparent surface)
                        let plotRect = CGRect(x: padL, y: padT, width: plotW, height: plotH)
                        ctx.fill(Path(plotRect), with: .color(Color.black.opacity(0.2)))
                        ctx.stroke(Path(plotRect), with: .color(Color.white.opacity(0.1)), lineWidth: 1)

                        // Vertical Grid Lines (Log Frequencies)
                        let xTicks: [Double] = [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]
                        let xLabels: [Double: String] = [
                            20: "20", 50: "50", 100: "100", 200: "200", 500: "500",
                            1000: "1k", 2000: "2k", 5000: "5k", 10000: "10k", 20000: "20k"
                        ]

                        for freq in xTicks {
                            let x = padL + CGFloat((log10(freq) - logMin) / (logMax - logMin)) * plotW
                            var gridLine = Path()
                            gridLine.move(to: CGPoint(x: x, y: padT))
                            gridLine.addLine(to: CGPoint(x: x, y: padT + plotH))
                            ctx.stroke(gridLine, with: .color(Color.white.opacity(0.06)), lineWidth: 1)

                            if let label = xLabels[freq] {
                                let text = Text(label)
                                    .font(.system(size: 9, design: .monospaced))
                                    .foregroundColor(.secondary)
                                ctx.draw(text, at: CGPoint(x: x, y: padT + plotH + 12), anchor: .center)
                            }
                        }

                        // Horizontal Grid Lines (dB)
                        var step = 5.0
                        let span = yMax - yMin
                        if span > 40 { step = 10.0 } else if span < 16 { step = 2.0 }

                        var db = floor(yMin / step) * step
                        while db <= yMax + 0.1 {
                            let y = padT + CGFloat((yMax - db) / (yMax - yMin)) * plotH
                            if y >= padT - 1 && y <= padT + plotH + 1 {
                                var hLine = Path()
                                hLine.move(to: CGPoint(x: padL, y: y))
                                hLine.addLine(to: CGPoint(x: padL + plotW, y: y))
                                ctx.stroke(hLine, with: .color(Color.white.opacity(0.06)), lineWidth: 1)

                                let dbLabel = Text(String(format: "%.0f", db))
                                    .font(.system(size: 9, design: .monospaced))
                                    .foregroundColor(.secondary)
                                ctx.draw(dbLabel, at: CGPoint(x: padL - 6, y: y), anchor: .trailing)
                            }
                            db += step
                        }

                        // Draw Curves
                        if let result = appState.correctionResult {
                            let freqs = result.gridFreqs
                            drawCurve(ctx: ctx, freqs: freqs, mags: result.sourceCurve, color: Color(white: 0.6), lineWidth: 1.8, padL: padL, padT: padT, plotW: plotW, plotH: plotH, yMin: yMin, yMax: yMax)
                            drawCurve(ctx: ctx, freqs: freqs, mags: result.targetCurve, color: Color.white, lineWidth: 1.8, padL: padL, padT: padT, plotW: plotW, plotH: plotH, yMin: yMin, yMax: yMax)
                            drawCurve(ctx: ctx, freqs: freqs, mags: result.simulatedCurve, color: Color(red: 0.35, green: 0.85, blue: 0.75), lineWidth: 2.2, padL: padL, padT: padT, plotW: plotW, plotH: plotH, yMin: yMin, yMax: yMax)
                        } else {
                            let emptyText = Text("选择耳机后点击「拟合校正曲线」生成频响")
                                .font(.system(size: 12))
                                .foregroundColor(.secondary)
                            ctx.draw(emptyText, at: CGPoint(x: padL + plotW / 2, y: padT + plotH / 2), anchor: .center)
                        }

                        // Hover Cursor line
                        if let hover = hoverLocation, hover.x >= padL && hover.x <= padL + plotW {
                            var cursorLine = Path()
                            cursorLine.move(to: CGPoint(x: hover.x, y: padT))
                            cursorLine.addLine(to: CGPoint(x: hover.x, y: padT + plotH))
                            ctx.stroke(cursorLine, with: .color(Color.white.opacity(0.6)), style: StrokeStyle(lineWidth: 1, dash: [4, 4]))
                        }
                    }

                    // Hover interaction overlay
                    Color.clear
                        .contentShape(Rectangle())
                        .gesture(
                            DragGesture(minimumDistance: 0)
                                .onChanged { val in
                                    let x = val.location.x
                                    if x >= padL && x <= padL + plotW {
                                        hoverLocation = val.location
                                        let normX = Double((x - padL) / plotW)
                                        let freq = pow(10.0, logMin + normX * (logMax - logMin))
                                        hoverFreq = min(max(freq, 20.0), 20000.0)
                                    }
                                }
                                .onEnded { _ in
                                    hoverLocation = nil
                                    hoverFreq = nil
                                }
                        )
                }
            }
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

    private func legendItem(title: String, color: Color) -> some View {
        HStack(spacing: 6) {
            RoundedRectangle(cornerRadius: 2)
                .fill(color)
                .frame(width: 14, height: 3)
            Text(title)
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(.primary)
        }
    }

    private func computeYBounds() -> (min: Double, max: Double) {
        guard let res = appState.correctionResult else {
            return (-15.0, 15.0)
        }
        var allVals: [Double] = []
        allVals.append(contentsOf: res.sourceCurve)
        allVals.append(contentsOf: res.targetCurve)
        allVals.append(contentsOf: res.simulatedCurve)

        guard let minV = allVals.min(), let maxV = allVals.max() else {
            return (-15.0, 15.0)
        }

        var yMin = minV - 3.0
        var yMax = maxV + 3.0
        if yMax - yMin < 8.0 {
            let mid = 0.5 * (yMin + yMax)
            yMin = mid - 4.0
            yMax = mid + 4.0
        }
        return (yMin, yMax)
    }

    private func drawCurve(
        ctx: GraphicsContext,
        freqs: [Double],
        mags: [Double],
        color: Color,
        lineWidth: CGFloat,
        padL: CGFloat,
        padT: CGFloat,
        plotW: CGFloat,
        plotH: CGFloat,
        yMin: Double,
        yMax: Double
    ) {
        guard freqs.count == mags.count && freqs.count > 1 else { return }

        var path = Path()
        var started = false

        for i in 0..<freqs.count {
            let f = freqs[i]
            let m = mags[i]
            if !f.isFinite || !m.isFinite || f < fMin || f > fMax { continue }

            let x = padL + CGFloat((log10(f) - logMin) / (logMax - logMin)) * plotW
            let y = padT + CGFloat((yMax - m) / (yMax - yMin)) * plotH

            if !started {
                path.move(to: CGPoint(x: x, y: y))
                started = true
            } else {
                path.addLine(to: CGPoint(x: x, y: y))
            }
        }

        ctx.stroke(path, with: .color(color), lineWidth: lineWidth)
    }
}
