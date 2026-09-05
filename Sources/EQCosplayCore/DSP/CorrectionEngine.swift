import Foundation

public enum CorrectionEngine {
    public static func calculateCorrection(
        sourceFreqs: [Double],
        sourceMags: [Double],
        targetFreqs: [Double],
        targetMags: [Double],
        fs: Double = 48000.0
    ) -> CorrectionResult {
        let gridFreqs = LogGrid.makeLogFreqs(numPoints: 512)
        let sourceInterp = LogGrid.interp(x: gridFreqs, xp: sourceFreqs, yp: sourceMags)
        let targetInterp = LogGrid.interp(x: gridFreqs, xp: targetFreqs, yp: targetMags)

        var deltaRaw = [Double](repeating: 0.0, count: 512)
        for i in 0..<512 {
            deltaRaw[i] = targetInterp[i] - sourceInterp[i]
        }

        let (deltaAligned, levelOffset) = Smoothing.alignDeltaLevel(freqs: gridFreqs, deltaDb: deltaRaw)
        let deltaForIIR = Smoothing.smoothCurveLogF(freqs: gridFreqs, curve: deltaAligned, octaves: 1.0 / 6.0)
        let deltaForGate = Smoothing.smoothCurveLogF(freqs: gridFreqs, curve: deltaAligned, octaves: 1.0 / 8.0)

        let (criticalNeedsFir, criticalStats) = PerceptualWeights.analyzeCriticalBandDifferences(
            freqs: gridFreqs,
            delta: deltaForGate
        )

        let preferRegions: [(Double, Double)]? = {
            let list = criticalStats.filter { $0.isLarge }.map { ($0.fLo, $0.fHi) }
            return list.isEmpty ? nil : list
        }()

        let initialBands = PEQOptimizer.initializeBands(
            freqs: gridFreqs,
            delta: deltaForIIR,
            fs: fs,
            criticalStats: criticalStats
        )

        let (fittedBands, peqRmseSmooth) = PEQOptimizer.optimizeBands(
            freqs: gridFreqs,
            delta: deltaForIIR,
            initialBands: initialBands,
            fs: fs,
            maxIterations: 60,
            boostRegions: preferRegions
        )

        let peqResp = Biquad.peqResponseDb(bands: fittedBands, freqs: gridFreqs, fs: fs)

        var sumSqPeq = 0.0
        var residualVsAligned = [Double](repeating: 0.0, count: 512)
        for i in 0..<512 {
            let diff = peqResp[i] - deltaAligned[i]
            sumSqPeq += diff * diff
            residualVsAligned[i] = deltaAligned[i] - peqResp[i]
        }
        let peqRmse = sqrt(sumSqPeq / 512.0)

        var needsFir = criticalNeedsFir
        if peqRmse >= 1.15 {
            needsFir = true
        }

        var firIr: [Double]? = nil
        var firTaps = 0
        var firRmse = 0.0
        var combinedRmse = peqRmse
        var combinedResp = peqResp

        if needsFir {
            let residualTarget = Smoothing.smoothCurveLogF(
                freqs: gridFreqs,
                curve: residualVsAligned,
                octaves: 1.0 / 12.0
            )
            let ir = FIRDesigner.designFir(freqs: gridFreqs, residualDb: residualTarget, fs: fs, nTaps: 8192)
            let firResp = FIRDesigner.firResponseDb(freqs: gridFreqs, ir: ir, fs: fs)

            var sumSqFir = 0.0
            var sumSqComb = 0.0
            var comb = [Double](repeating: 0.0, count: 512)

            for i in 0..<512 {
                let fDiff = firResp[i] - residualVsAligned[i]
                sumSqFir += fDiff * fDiff

                let cVal = peqResp[i] + firResp[i]
                comb[i] = cVal
                let cDiff = cVal - deltaAligned[i]
                sumSqComb += cDiff * cDiff
            }

            firIr = ir
            firTaps = ir.count
            firRmse = sqrt(sumSqFir / 512.0)
            combinedResp = comb
            combinedRmse = sqrt(sumSqComb / 512.0)
        }

        var peak = -Double.infinity
        var valley = Double.infinity
        var simulatedCurve = [Double](repeating: 0.0, count: 512)

        for i in 0..<512 {
            let v = combinedResp[i]
            if v > peak { peak = v }
            if v < valley { valley = v }
            simulatedCurve[i] = sourceInterp[i] + v
        }

        return CorrectionResult(
            peqBands: fittedBands,
            peqRmse: peqRmse,
            peqRmseSmooth: peqRmseSmooth,
            useFir: needsFir && firIr != nil,
            firIr: firIr,
            firTaps: firTaps,
            firRmse: firRmse,
            combinedRmse: combinedRmse,
            responsePeak: peak,
            responseValley: valley,
            levelOffsetDb: levelOffset,
            needsFir: needsFir,
            criticalStats: criticalStats,
            gridFreqs: gridFreqs,
            sourceCurve: sourceInterp,
            targetCurve: targetInterp,
            simulatedCurve: simulatedCurve,
            peqResponse: peqResp
        )
    }

    public static func createResultFromPreset(
        bands: [PEQBand],
        firIr: [Double]?,
        metrics: [String: Double],
        fs: Double = 48000.0,
        useFir: Bool = false
    ) -> CorrectionResult {
        let gridFreqs = LogGrid.makeLogFreqs(numPoints: 512)
        let peqResp = Biquad.peqResponseDb(bands: bands, freqs: gridFreqs, fs: fs)

        var combinedResp = peqResp
        if useFir, let ir = firIr, !ir.isEmpty {
            let firResp = FIRDesigner.firResponseDb(freqs: gridFreqs, ir: ir, fs: fs)
            for i in 0..<512 {
                combinedResp[i] = peqResp[i] + firResp[i]
            }
        }

        var peak = -Double.infinity
        var valley = Double.infinity
        for v in combinedResp {
            if v > peak { peak = v }
            if v < valley { valley = v }
        }
        if peak.isInfinite { peak = 0.0 }
        if valley.isInfinite { valley = 0.0 }

        let peqRmse = metrics["peq_rmse"] ?? 0.0
        let combinedRmse = metrics["combined_rmse"] ?? peqRmse
        let responsePeak = metrics["response_peak"] ?? peak

        return CorrectionResult(
            peqBands: bands,
            peqRmse: peqRmse,
            peqRmseSmooth: peqRmse,
            useFir: useFir && (firIr != nil && !(firIr!.isEmpty)),
            firIr: firIr,
            firTaps: firIr?.count ?? 0,
            firRmse: 0.0,
            combinedRmse: combinedRmse,
            responsePeak: responsePeak,
            responseValley: valley,
            levelOffsetDb: 0.0,
            needsFir: firIr != nil && !(firIr!.isEmpty),
            criticalStats: [],
            gridFreqs: gridFreqs,
            sourceCurve: [Double](repeating: 0.0, count: 512),
            targetCurve: combinedResp,
            simulatedCurve: combinedResp,
            peqResponse: peqResp
        )
    }
}
