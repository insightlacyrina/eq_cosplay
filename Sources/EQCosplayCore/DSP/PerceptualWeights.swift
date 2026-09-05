import Foundation

public enum PerceptualWeights {
    public static func weights(freqs: [Double], boostRegions: [(Double, Double)]? = nil) -> [Double] {
        var result = [Double](repeating: 1.0, count: freqs.count)

        for i in 0..<freqs.count {
            let f = min(max(freqs[i], 20.0), 20000.0)
            let logf = log10(f)

            let broad = exp(-0.5 * pow((logf - log10(1000.0)) / 0.85, 2.0))
            let presence = exp(-0.5 * pow((logf - log10(2500.0)) / 0.40, 2.0))
            let bass = exp(-0.5 * pow((logf - log10(100.0)) / 0.45, 2.0))
            let treble = exp(-0.5 * pow((logf - log10(7000.0)) / 0.45, 2.0))
            let air = exp(-0.5 * pow((logf - log10(14000.0)) / 0.30, 2.0))

            var w = 0.30 + 0.48 * broad + 0.22 * presence + 0.16 * bass + 0.10 * treble - 0.08 * air
            w = max(w, 0.12)

            if let regions = boostRegions {
                for (fLo, fHi) in regions {
                    if f >= fLo && f <= fHi {
                        w *= 1.20
                    }
                }
            }
            result[i] = w
        }

        let meanW = result.reduce(0.0, +) / Double(max(result.count, 1))
        let normW = meanW > 0 ? result.map { $0 / meanW } : result
        return normW
    }

    public static func analyzeCriticalBandDifferences(
        freqs: [Double],
        delta: [Double]
    ) -> (needsFir: Bool, stats: [CriticalBandStat]) {
        let bands: [(Double, Double, String)] = [
            (60.0, 150.0, "60-150Hz"),
            (200.0, 600.0, "200-600Hz"),
            (2000.0, 4000.0, "2-4kHz"),
            (5000.0, 10000.0, "5-10kHz")
        ]

        let maxAbsThreshold = 3.5
        let ptpThreshold = 4.0
        let rmsThreshold = 2.2

        var stats: [CriticalBandStat] = []
        var anyLarge = false

        for (fLo, fHi, name) in bands {
            var bandDeltas: [Double] = []
            for i in 0..<freqs.count {
                if freqs[i] >= fLo && freqs[i] <= fHi {
                    bandDeltas.append(delta[i])
                }
            }

            if bandDeltas.isEmpty {
                stats.append(CriticalBandStat(name: name, fLo: fLo, fHi: fHi, maxAbs: 0, ptp: 0, rms: 0, isLarge: false))
                continue
            }

            var maxAbs = 0.0
            var minVal = bandDeltas[0]
            var maxVal = bandDeltas[0]
            var sumSq = 0.0

            for v in bandDeltas {
                let absV = abs(v)
                if absV > maxAbs { maxAbs = absV }
                if v < minVal { minVal = v }
                if v > maxVal { maxVal = v }
                sumSq += v * v
            }

            let ptp = maxVal - minVal
            let rms = sqrt(sumSq / Double(bandDeltas.count))
            let isLarge = maxAbs >= maxAbsThreshold || ptp >= ptpThreshold || rms >= rmsThreshold
            if isLarge {
                anyLarge = true
            }

            stats.append(CriticalBandStat(
                name: name,
                fLo: fLo,
                fHi: fHi,
                maxAbs: maxAbs,
                ptp: ptp,
                rms: rms,
                isLarge: isLarge
            ))
        }

        return (anyLarge, stats)
    }
}
