import Foundation

public struct BiquadCoeffs: Sendable {
    public let b0: Double
    public let b1: Double
    public let b2: Double
    public let a1: Double
    public let a2: Double

    public init(type: FilterType, f0: Double, gainDb: Double, q: Double, fs: Double) {
        let A = pow(10.0, gainDb / 40.0)
        let w0 = 2.0 * Double.pi * f0 / fs
        let safeQ = max(q, 1e-4)
        let alpha = sin(w0) / (2.0 * safeQ)
        let cosW0 = cos(w0)

        var b0Raw: Double = 0
        var b1Raw: Double = 0
        var b2Raw: Double = 0
        var a0Raw: Double = 1
        var a1Raw: Double = 0
        var a2Raw: Double = 0

        switch type {
        case .peaking:
            b0Raw = 1.0 + alpha * A
            b1Raw = -2.0 * cosW0
            b2Raw = 1.0 - alpha * A
            a0Raw = 1.0 + alpha / A
            a1Raw = -2.0 * cosW0
            a2Raw = 1.0 - alpha / A

        case .lowshelf:
            let sqrtA = sqrt(A)
            b0Raw = A * ((A + 1.0) - (A - 1.0) * cosW0 + 2.0 * sqrtA * alpha)
            b1Raw = 2.0 * A * ((A - 1.0) - (A + 1.0) * cosW0)
            b2Raw = A * ((A + 1.0) - (A - 1.0) * cosW0 - 2.0 * sqrtA * alpha)
            a0Raw = (A + 1.0) + (A - 1.0) * cosW0 + 2.0 * sqrtA * alpha
            a1Raw = -2.0 * ((A - 1.0) + (A + 1.0) * cosW0)
            a2Raw = (A + 1.0) + (A - 1.0) * cosW0 - 2.0 * sqrtA * alpha

        case .highshelf:
            let sqrtA = sqrt(A)
            b0Raw = A * ((A + 1.0) + (A - 1.0) * cosW0 + 2.0 * sqrtA * alpha)
            b1Raw = -2.0 * A * ((A - 1.0) + (A + 1.0) * cosW0)
            b2Raw = A * ((A + 1.0) + (A - 1.0) * cosW0 - 2.0 * sqrtA * alpha)
            a0Raw = (A + 1.0) - (A - 1.0) * cosW0 + 2.0 * sqrtA * alpha
            a1Raw = 2.0 * ((A - 1.0) - (A + 1.0) * cosW0)
            a2Raw = (A + 1.0) - (A - 1.0) * cosW0 - 2.0 * sqrtA * alpha
        }

        let invA0 = 1.0 / a0Raw
        self.b0 = b0Raw * invA0
        self.b1 = b1Raw * invA0
        self.b2 = b2Raw * invA0
        self.a1 = a1Raw * invA0
        self.a2 = a2Raw * invA0
    }

    /// Evaluates frequency response in dB at a given frequency f
    public func responseDb(at frequency: Double, fs: Double) -> Double {
        let w = 2.0 * Double.pi * frequency / fs
        let cosW = cos(w)
        let sinW = sin(w)
        let cos2W = cos(2.0 * w)
        let sin2W = sin(2.0 * w)

        // H(e^jw) = (b0 + b1 e^-jw + b2 e^-2jw) / (1 + a1 e^-jw + a2 e^-2jw)
        let numRe = b0 + b1 * cosW + b2 * cos2W
        let numIm = -b1 * sinW - b2 * sin2W

        let denRe = 1.0 + a1 * cosW + a2 * cos2W
        let denIm = -a1 * sinW - a2 * sin2W

        let numMag2 = numRe * numRe + numIm * numIm
        let denMag2 = max(denRe * denRe + denIm * denIm, 1e-24)

        let mag = sqrt(numMag2 / denMag2)
        return 20.0 * log10(max(mag, 1e-12))
    }
}

public enum Biquad {
    public static func responseDb(type: FilterType, f0: Double, gainDb: Double, q: Double, freqs: [Double], fs: Double) -> [Double] {
        let coeffs = BiquadCoeffs(type: type, f0: f0, gainDb: gainDb, q: q, fs: fs)
        return freqs.map { coeffs.responseDb(at: $0, fs: fs) }
    }

    public static func peqResponseDb(bands: [PEQBand], freqs: [Double], fs: Double) -> [Double] {
        var total = [Double](repeating: 0.0, count: freqs.count)
        for band in bands {
            let resp = responseDb(type: band.type, f0: band.frequency, gainDb: band.gain, q: band.q, freqs: freqs, fs: fs)
            for i in 0..<freqs.count {
                total[i] += resp[i]
            }
        }
        return total
    }
}
