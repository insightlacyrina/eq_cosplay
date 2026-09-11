import Foundation

public enum PEQOptimizer {
    public static let numPeaking = 8
    public static let gainMin = -10.0
    public static let gainMax = 10.0
    public static let qPeakMin = 0.35
    public static let qPeakMax = 4.0
    public static let qShelfMin = 0.5
    public static let qShelfMax = 1.4
    public static let minOctaveSep = 0.38
    public static let maxLowPeaking = 3

    public static func octaveDistance(_ f1: Double, _ f2: Double) -> Double {
        abs(log2(max(f1, 1e-6) / max(f2, 1e-6)))
    }

    /// Initializes 10 PEQ bands (1 Lowshelf + 8 Peaking + 1 Highshelf) based on residual extrema
    public static func initializeBands(
        freqs: [Double],
        delta: [Double],
        fs: Double,
        criticalStats: [CriticalBandStat]? = nil
    ) -> [PEQBand] {
        var residual = delta

        // 1) Low Shelf (20 - 120 Hz)
        var lowGainSum = 0.0
        var lowGainCount = 0
        for i in 0..<freqs.count where freqs[i] >= 20.0 && freqs[i] <= 120.0 {
            lowGainSum += residual[i]
            lowGainCount += 1
        }
        var lowGain = lowGainCount > 0 ? (lowGainSum / Double(lowGainCount)) : 0.0
        lowGain = min(max(lowGain, gainMin), gainMax)

        var lowFc = 60.0
        if abs(lowGain) > 0.2 {
            var sumW = 0.0
            var sumWLogF = 0.0
            for i in 0..<freqs.count where freqs[i] >= 20.0 && freqs[i] <= 120.0 {
                let w = abs(residual[i]) + 0.1
                sumW += w
                sumWLogF += w * log(freqs[i])
            }
            if sumW > 0 {
                lowFc = exp(sumWLogF / sumW)
            }
        }
        lowFc = min(max(lowFc, 25.0), 250.0)
        let lowBand = PEQBand(type: .lowshelf, frequency: lowFc, gain: lowGain, q: 0.7)
        let lowResp = Biquad.responseDb(type: .lowshelf, f0: lowFc, gainDb: lowGain, q: 0.7, freqs: freqs, fs: fs)
        for i in 0..<residual.count {
            residual[i] -= lowResp[i]
        }

        // 2) High Shelf (6000 - 14000 Hz)
        var highGainSum = 0.0
        var highGainCount = 0
        for i in 0..<freqs.count where freqs[i] >= 6000.0 && freqs[i] <= 14000.0 {
            highGainSum += residual[i]
            highGainCount += 1
        }
        var highGain = highGainCount > 0 ? (highGainSum / Double(highGainCount)) : 0.0
        highGain = min(max(highGain, gainMin), gainMax)

        var highFc = 9000.0
        if abs(highGain) > 0.2 {
            var sumW = 0.0
            var sumWLogF = 0.0
            for i in 0..<freqs.count where freqs[i] >= 6000.0 && freqs[i] <= 14000.0 {
                let w = abs(residual[i]) + 0.1
                sumW += w
                sumWLogF += w * log(freqs[i])
            }
            if sumW > 0 {
                highFc = exp(sumWLogF / sumW)
            }
        }
        highFc = min(max(highFc, 4000.0), 14000.0)
        let highBand = PEQBand(type: .highshelf, frequency: highFc, gain: highGain, q: 0.7)
        let highResp = Biquad.responseDb(type: .highshelf, f0: highFc, gainDb: highGain, q: 0.7, freqs: freqs, fs: fs)
        for i in 0..<residual.count {
            residual[i] -= highResp[i]
        }

        let preferRegions: [(Double, Double)] = (criticalStats ?? [])
            .filter { $0.isLarge }
            .map { ($0.fLo, $0.fHi) }

        let selectedPairs = findResidualExtrema(
            freqs: freqs,
            residual: residual,
            nPeaks: numPeaking,
            existingFreqs: [lowFc, highFc],
            preferRegions: preferRegions.isEmpty ? nil : preferRegions
        )

        var selectedPeaking: [PEQBand] = []
        for (idx, mag) in selectedPairs.prefix(numPeaking) {
            let f0 = min(max(freqs[idx], 30.0), 14000.0)
            let gain = min(max(mag, gainMin), gainMax)
            let q = estimateQFromBandwidth(freqs: freqs, curve: residual, peakIndex: idx)
            selectedPeaking.append(PEQBand(type: .peaking, frequency: f0, gain: gain, q: q))
        }

        selectedPeaking.sort { $0.frequency < $1.frequency }
        var allBands = [lowBand]
        allBands.append(contentsOf: selectedPeaking)
        allBands.append(highBand)
        return allBands
    }

    /// Optimized Levenberg-Marquardt fitting of 10 PEQ bands (30 parameters)
    public static func optimizeBands(
        freqs: [Double],
        delta: [Double],
        initialBands: [PEQBand],
        fs: Double,
        maxIterations: Int = 60,
        boostRegions: [(Double, Double)]? = nil
    ) -> (bands: [PEQBand], rmse: Double) {
        let weights = PerceptualWeights.weights(freqs: freqs, boostRegions: boostRegions)
        let numBands = initialBands.count
        let numParams = numBands * 3

        // Pack parameters: [gain, log10(fc), log10(q)]
        var x = [Double](repeating: 0.0, count: numParams)
        var types = [FilterType]()

        for (i, b) in initialBands.enumerated() {
            types.append(b.type)
            x[3 * i + 0] = b.gain
            x[3 * i + 1] = log10(max(b.frequency, 10.0))
            x[3 * i + 2] = log10(max(b.q, 0.1))
        }

        func unpack(_ p: [Double]) -> [PEQBand] {
            var res: [PEQBand] = []
            for i in 0..<numBands {
                let g = p[3 * i + 0]
                let fc = pow(10.0, p[3 * i + 1])
                let q = pow(10.0, p[3 * i + 2])
                res.append(PEQBand(type: types[i], frequency: fc, gain: g, q: q))
            }
            return res
        }

        func clampParams(_ p: inout [Double]) {
            for i in 0..<numBands {
                // gain clamp
                p[3 * i + 0] = min(max(p[3 * i + 0], gainMin), gainMax)

                let type = types[i]
                switch type {
                case .lowshelf:
                    p[3 * i + 1] = min(max(p[3 * i + 1], log10(20.0)), log10(300.0))
                    p[3 * i + 2] = min(max(p[3 * i + 2], log10(qShelfMin)), log10(qShelfMax))
                case .highshelf:
                    p[3 * i + 1] = min(max(p[3 * i + 1], log10(4000.0)), log10(14000.0))
                    p[3 * i + 2] = min(max(p[3 * i + 2], log10(qShelfMin)), log10(qShelfMax))
                case .peaking:
                    p[3 * i + 1] = min(max(p[3 * i + 1], log10(25.0)), log10(14000.0))
                    p[3 * i + 2] = min(max(p[3 * i + 2], log10(qPeakMin)), log10(qPeakMax))
                }
            }
        }

        clampParams(&x)

        // Residual calculation
        func computeResidual(_ p: [Double]) -> [Double] {
            let bands = unpack(p)
            let pred = Biquad.peqResponseDb(bands: bands, freqs: freqs, fs: fs)
            var r = [Double](repeating: 0.0, count: freqs.count)
            // soft_l1 (f_scale=2.5), matching scipy.optimize.least_squares in the Python sibling.
            // IRLS form: r / (1 + (r/f_scale)^2)^0.25 downweights 10 kHz+ measurement spikes.
            let fScale = 2.5
            for i in 0..<freqs.count {
                let raw = (pred[i] - delta[i]) * weights[i]
                let z = (raw / fScale) * (raw / fScale)
                r[i] = raw / pow(1.0 + z, 0.25)
            }

            // Regularization penalties
            var penalties: [Double] = []
            var peakFcs: [Double] = []

            for i in 0..<numBands {
                let g = abs(p[3 * i + 0])
                penalties.append(0.18 * pow(max(0.0, g - 5.0), 1.35))
                penalties.append(0.04 * g)

                let type = types[i]
                if type == .peaking {
                    let q = pow(10.0, p[3 * i + 2])
                    penalties.append(0.18 * pow(max(0.0, q - 2.4), 1.2))
                    penalties.append(0.06 * max(0.0, q - 3.2))
                    peakFcs.append(pow(10.0, p[3 * i + 1]))
                } else {
                    let q = pow(10.0, p[3 * i + 2])
                    penalties.append(0.06 * max(0.0, q - 1.0))
                }
            }

            peakFcs.sort()
            if peakFcs.count >= 2 {
                for i in 0..<(peakFcs.count - 1) {
                    let sep = octaveDistance(peakFcs[i], peakFcs[i + 1])
                    penalties.append(0.30 * max(0.0, minOctaveSep - sep))
                }
            }

            r.append(contentsOf: penalties)
            return r
        }

        func sumSquared(_ v: [Double]) -> Double {
            var s = 0.0
            for x in v { s += x * x }
            return s
        }

        let eps = 1e-4

        func runLM(iterations: Int) {
            var currentRes = computeResidual(x)
            var currentCost = sumSquared(currentRes)
            var lambda = 1e-2

            for _ in 0..<iterations {
                let m = currentRes.count
                let n = numParams

                var J = [Double](repeating: 0.0, count: m * n)
                for j in 0..<n {
                    var xPerturbed = x
                    let step = max(abs(x[j]) * eps, eps)
                    xPerturbed[j] += step
                    let resPerturbed = computeResidual(xPerturbed)
                    for i in 0..<m {
                        J[i * n + j] = (resPerturbed[i] - currentRes[i]) / step
                    }
                }

                var JtJ = [Double](repeating: 0.0, count: n * n)
                var g = [Double](repeating: 0.0, count: n)

                for j1 in 0..<n {
                    var sumG = 0.0
                    for i in 0..<m {
                        sumG += J[i * n + j1] * currentRes[i]
                    }
                    g[j1] = -sumG

                    for j2 in j1..<n {
                        var sumJtJ = 0.0
                        for i in 0..<m {
                            sumJtJ += J[i * n + j1] * J[i * n + j2]
                        }
                        JtJ[j1 * n + j2] = sumJtJ
                        JtJ[j2 * n + j1] = sumJtJ
                    }
                }

                var A = JtJ
                for j in 0..<n {
                    A[j * n + j] += lambda * max(JtJ[j * n + j], 1e-3)
                }

                guard let deltaP = solveLinearSystem(A: A, b: g, n: n) else {
                    lambda *= 10.0
                    continue
                }

                var xCandidate = x
                for j in 0..<n {
                    xCandidate[j] += deltaP[j]
                }
                clampParams(&xCandidate)

                let candidateRes = computeResidual(xCandidate)
                let candidateCost = sumSquared(candidateRes)

                if candidateCost < currentCost {
                    let improvement = currentCost - candidateCost
                    x = xCandidate
                    currentRes = candidateRes
                    currentCost = candidateCost
                    lambda = max(lambda / 5.0, 1e-6)
                    if improvement < 1e-8 * max(currentCost, 1.0) {
                        break
                    }
                } else {
                    lambda = min(lambda * 5.0, 1e5)
                }
            }
        }

        runLM(iterations: maxIterations)

        var fittedBands = unpack(x)
        enforcePeakingSeparation(&fittedBands)
        for (i, b) in fittedBands.enumerated() {
            x[3 * i + 0] = b.gain
            x[3 * i + 1] = log10(max(b.frequency, 10.0))
            x[3 * i + 2] = log10(max(b.q, 0.1))
        }
        clampParams(&x)
        runLM(iterations: max(20, maxIterations / 3))

        fittedBands = unpack(x)
        enforcePeakingSeparation(&fittedBands)

        // Final RMSE against unweighted delta
        let finalPred = Biquad.peqResponseDb(bands: fittedBands, freqs: freqs, fs: fs)
        var sumSqErr = 0.0
        for i in 0..<freqs.count {
            let err = finalPred[i] - delta[i]
            sumSqErr += err * err
        }
        let rmse = sqrt(sumSqErr / Double(freqs.count))

        // Clean values: round fc to 1 dec, gain to 2 dec, Q to 2 dec
        let roundedBands = fittedBands.map { b in
            PEQBand(
                id: b.id,
                type: b.type,
                frequency: round(b.frequency * 10.0) / 10.0,
                gain: round(b.gain * 100.0) / 100.0,
                q: round(b.q * 100.0) / 100.0
            )
        }

        return (roundedBands, rmse)
    }

    /// Residual extrema for peaking seeds: plateau-tolerant, octave-separated, low-band capped.
    static func findResidualExtrema(
        freqs: [Double],
        residual: [Double],
        nPeaks: Int,
        existingFreqs: [Double],
        preferRegions: [(Double, Double)]?,
        fLo: Double? = nil,
        fHi: Double? = nil
    ) -> [(Int, Double)] {
        let n = residual.count
        var candidates: [(score: Double, index: Int, mag: Double)] = []

        for i in 1..<(n - 1) {
            let f = freqs[i]
            if let fLo, f < fLo { continue }
            if let fHi, f > fHi { continue }
            let r = residual[i]
            let isMax = residual[i] >= residual[i - 1] && residual[i] >= residual[i + 1]
            let isMin = residual[i] <= residual[i - 1] && residual[i] <= residual[i + 1]
            if !(isMax || isMin) { continue }
            if abs(r) < 0.25 { continue }

            var score = abs(r)
            if f > 12000.0 {
                score *= 0.45
            } else if f > 10000.0 {
                score *= 0.70
            } else if f < 40.0 {
                score *= 0.65
            }
            if let regions = preferRegions {
                for (prLo, prHi) in regions where f >= prLo && f <= prHi {
                    score *= 1.28
                    break
                }
            }
            candidates.append((score, i, r))
        }

        candidates.sort { $0.score > $1.score }

        var selected: [(Int, Double)] = []
        var selectedFreqs = existingFreqs
        var lowCount = selectedFreqs.filter { $0 < 300.0 }.count

        for item in candidates {
            if selected.count >= nPeaks { break }
            let f = freqs[item.index]
            if selectedFreqs.contains(where: { octaveDistance($0, f) < minOctaveSep }) { continue }
            if f < 300.0 && lowCount >= maxLowPeaking { continue }
            selected.append((item.index, item.mag))
            selectedFreqs.append(f)
            if f < 300.0 { lowCount += 1 }
        }

        if selected.count < nPeaks {
            let gLo = max(fLo ?? 80.0, 30.0)
            let gHi = min(fHi ?? 10000.0, 12000.0)
            if gHi > gLo {
                let gridCount = max(nPeaks * 4, 8)
                let logLo = log10(gLo)
                let logHi = log10(gHi)
                for k in 0..<gridCount {
                    if selected.count >= nPeaks { break }
                    let t = Double(k) / Double(max(gridCount - 1, 1))
                    let f = pow(10.0, logLo + t * (logHi - logLo))
                    if selectedFreqs.contains(where: { octaveDistance($0, f) < minOctaveSep }) { continue }
                    if f < 300.0 && lowCount >= maxLowPeaking { continue }
                    var bestIdx = 0
                    var bestDiff = Double.infinity
                    for i in 0..<freqs.count {
                        let d = abs(freqs[i] - f)
                        if d < bestDiff {
                            bestDiff = d
                            bestIdx = i
                        }
                    }
                    selected.append((bestIdx, residual[bestIdx]))
                    selectedFreqs.append(freqs[bestIdx])
                    if f < 300.0 { lowCount += 1 }
                }
            }
        }

        return Array(selected.prefix(nPeaks))
    }

    /// Estimate peaking Q from local -3 dB (or 50% for small peaks) bandwidth.
    static func estimateQFromBandwidth(freqs: [Double], curve: [Double], peakIndex: Int) -> Double {
        let n = curve.count
        let idx = min(max(peakIndex, 0), n - 1)
        let f0 = freqs[idx]
        let peakVal = curve[idx]
        if abs(peakVal) < 0.35 {
            return 1.1
        }

        let thr = abs(peakVal) >= 3.0 ? (peakVal - 3.0 * (peakVal >= 0 ? 1.0 : -1.0)) : peakVal * 0.5

        func sideBoundary(direction: Int) -> Double {
            var i = idx
            while i > 0 && i < n - 1 {
                let j = i + direction
                let y0 = curve[i]
                let y1 = curve[j]
                let crossed = (peakVal > 0 && y1 <= thr) || (peakVal < 0 && y1 >= thr)
                if crossed {
                    if abs(y1 - y0) < 1e-12 {
                        return freqs[j]
                    }
                    let t = min(max((thr - y0) / (y1 - y0), 0.0), 1.0)
                    return freqs[i] + t * (freqs[j] - freqs[i])
                }
                i = j
            }
            return direction < 0 ? freqs[0] : freqs[n - 1]
        }

        let fLeft = sideBoundary(direction: -1)
        let fRight = sideBoundary(direction: 1)
        let bw = max(fRight - fLeft, f0 * 1e-3)
        var q = f0 / bw
        q = min(max(q, qPeakMin), qPeakMax)
        if q > 2.8 {
            q = 2.8 + 0.45 * (q - 2.8)
        }
        return min(max(q, qPeakMin), qPeakMax)
    }

    public static func enforcePeakingSeparation(_ bands: inout [PEQBand]) {
        var peakingIndices = bands.indices.filter { bands[$0].type == .peaking }
        guard peakingIndices.count >= 2 else { return }

        peakingIndices.sort { bands[$0].frequency < bands[$1].frequency }

        for _ in 0..<8 {
            var moved = false
            for k in 0..<(peakingIndices.count - 1) {
                let idx1 = peakingIndices[k]
                let idx2 = peakingIndices[k + 1]
                let f1 = bands[idx1].frequency
                let f2 = bands[idx2].frequency
                let sep = octaveDistance(f1, f2)
                if sep < minOctaveSep {
                    let mid = sqrt(f1 * f2)
                    let halfSepRatio = pow(2.0, minOctaveSep / 2.0)
                    bands[idx1].frequency = min(max(mid / halfSepRatio, 25.0), 14000.0)
                    bands[idx2].frequency = min(max(mid * halfSepRatio, 25.0), 14000.0)
                    moved = true
                }
            }
            if !moved { break }
        }
    }

    private static func solveLinearSystem(A: [Double], b: [Double], n: Int) -> [Double]? {
        var a = A
        var x = b

        for i in 0..<n {
            // Find pivot
            var maxRow = i
            var maxVal = abs(a[i * n + i])
            for k in (i + 1)..<n {
                let val = abs(a[k * n + i])
                if val > maxVal {
                    maxVal = val
                    maxRow = k
                }
            }

            if maxVal < 1e-12 {
                return nil
            }

            // Swap rows
            if maxRow != i {
                for col in 0..<n {
                    let tmp = a[i * n + col]
                    a[i * n + col] = a[maxRow * n + col]
                    a[maxRow * n + col] = tmp
                }
                let tmpB = x[i]
                x[i] = x[maxRow]
                x[maxRow] = tmpB
            }

            // Eliminate
            for k in (i + 1)..<n {
                let factor = a[k * n + i] / a[i * n + i]
                x[k] -= factor * x[i]
                for col in i..<n {
                    a[k * n + col] -= factor * a[i * n + col]
                }
            }
        }

        // Back substitution
        for i in stride(from: n - 1, through: 0, by: -1) {
            var sum = x[i]
            for col in (i + 1)..<n {
                sum -= a[i * n + col] * x[col]
            }
            x[i] = sum / a[i * n + i]
        }

        return x
    }
}
