import Foundation

public enum Smoothing {
    /// Performs Gaussian smoothing on fractional octaves over logarithmic frequency
    public static func smoothCurveLogF(freqs: [Double], curve: [Double], octaves: Double) -> [Double] {
        guard octaves > 0 && freqs.count >= 3 && freqs.count == curve.count else {
            return curve
        }

        let logf = freqs.map { log2(max($0, 1e-6)) }
        let sigma = max(octaves / 2.355, 1e-6)
        let twoSigma2 = 2.0 * sigma * sigma

        var smoothed = [Double](repeating: 0.0, count: curve.count)

        for i in 0..<freqs.count {
            let targetLf = logf[i]
            var wSum = 0.0
            var valSum = 0.0

            for j in 0..<freqs.count {
                let diff = logf[j] - targetLf
                let w = exp(-(diff * diff) / twoSigma2)
                wSum += w
                valSum += w * curve[j]
            }

            smoothed[i] = wSum > 0 ? valSum / wSum : curve[i]
        }

        return smoothed
    }

    /// Removes measurement level offset by aligning average delta in reference band (default 200 - 2000 Hz) to 0 dB
    public static func alignDeltaLevel(
        freqs: [Double],
        deltaDb: [Double],
        bandLo: Double = 200.0,
        bandHi: Double = 2000.0
    ) -> (aligned: [Double], offset: Double) {
        guard freqs.count == deltaDb.count && !freqs.isEmpty else {
            return (deltaDb, 0.0)
        }

        var sum = 0.0
        var count = 0

        for i in 0..<freqs.count {
            let f = freqs[i]
            if f >= bandLo && f <= bandHi {
                sum += deltaDb[i]
                count += 1
            }
        }

        if count == 0 {
            for i in 0..<freqs.count {
                let f = freqs[i]
                if f >= 100.0 && f <= 5000.0 {
                    sum += deltaDb[i]
                    count += 1
                }
            }
        }

        let offset = count > 0 ? sum / Double(count) : 0.0
        let aligned = deltaDb.map { $0 - offset }
        return (aligned, offset)
    }
}
