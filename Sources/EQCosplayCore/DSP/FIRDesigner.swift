import Foundation

public struct ComplexD {
    public var re: Double
    public var im: Double

    public init(re: Double, im: Double = 0.0) {
        self.re = re
        self.im = im
    }

    public var magnitude: Double {
        sqrt(re * re + im * im)
    }

    public var phase: Double {
        atan2(im, re)
    }

    public static func + (lhs: ComplexD, rhs: ComplexD) -> ComplexD {
        ComplexD(re: lhs.re + rhs.re, im: lhs.im + rhs.im)
    }

    public static func - (lhs: ComplexD, rhs: ComplexD) -> ComplexD {
        ComplexD(re: lhs.re - rhs.re, im: lhs.im - rhs.im)
    }

    public static func * (lhs: ComplexD, rhs: ComplexD) -> ComplexD {
        ComplexD(
            re: lhs.re * rhs.re - lhs.im * rhs.im,
            im: lhs.re * rhs.im + lhs.im * rhs.re
        )
    }

    public static func * (lhs: ComplexD, scalar: Double) -> ComplexD {
        ComplexD(re: lhs.re * scalar, im: lhs.im * scalar)
    }
}

public enum FFT {
    /// In-place radix-2 Cooley-Tukey FFT (inverse = true for IFFT)
    public static func transform(_ data: inout [ComplexD], inverse: Bool = false) {
        let n = data.count
        guard n > 1 && (n & (n - 1)) == 0 else { return }

        // Bit-reversal permutation
        var j = 0
        for i in 0..<(n - 1) {
            if i < j {
                data.swapAt(i, j)
            }
            var k = n >> 1
            while k <= j {
                j -= k
                k >>= 1
            }
            j += k
        }

        // Cooley-Tukey butterfly
        var len = 2
        while len <= n {
            let half = len >> 1
            let angle = (inverse ? 2.0 : -2.0) * Double.pi / Double(len)
            let wstep = ComplexD(re: cos(angle), im: sin(angle))

            var i = 0
            while i < n {
                var w = ComplexD(re: 1.0, im: 0.0)
                for k in 0..<half {
                    let u = data[i + k]
                    let v = data[i + k + half] * w
                    data[i + k] = u + v
                    data[i + k + half] = u - v
                    w = w * wstep
                }
                i += len
            }
            len <<= 1
        }

        if inverse {
            let invN = 1.0 / Double(n)
            for i in 0..<n {
                data[i].re *= invN
                data[i].im *= invN
            }
        }
    }
}

public enum FIRDesigner {
    public static let defaultTaps = 8192
    public static let gainClipDb = 18.0

    /// Reconstructs minimum-phase impulse response from a linear magnitude spectrum using the real cepstrum
    public static func minPhaseFromMagnitude(magLin: [Double], nFft: Int) -> [Double] {
        let halfN = nFft / 2

        // 1. Build full symmetric log-magnitude spectrum
        var fullSpectrum = [ComplexD](repeating: ComplexD(re: 0.0), count: nFft)
        for k in 0...halfN {
            let m = max(magLin[k], 1e-12)
            let logM = log(m)
            fullSpectrum[k] = ComplexD(re: logM, im: 0.0)
            if k > 0 && k < halfN {
                fullSpectrum[nFft - k] = ComplexD(re: logM, im: 0.0)
            }
        }

        // 2. Real cepstrum c[n] = IFFT(log |H[k]|)
        FFT.transform(&fullSpectrum, inverse: true)

        // 3. Apply causal minimum-phase cepstral window
        // w[0] = 1, w[1..<halfN] = 2, w[halfN] = 1, w[halfN+1..<nFft] = 0
        fullSpectrum[0].im = 0.0
        for n in 1..<halfN {
            fullSpectrum[n].re *= 2.0
            fullSpectrum[n].im *= 2.0
        }
        fullSpectrum[halfN].im = 0.0
        for n in (halfN + 1)..<nFft {
            fullSpectrum[n] = ComplexD(re: 0.0, im: 0.0)
        }

        // 4. Transform back to frequency domain: FFT(c_min[n])
        FFT.transform(&fullSpectrum, inverse: false)

        // 5. Lock to original target magnitude with computed minimum phase angle
        for k in 0...halfN {
            let phaseAngle = fullSpectrum[k].im
            let m = magLin[k]
            let h = ComplexD(re: m * cos(phaseAngle), im: m * sin(phaseAngle))
            fullSpectrum[k] = h
            if k > 0 && k < halfN {
                fullSpectrum[nFft - k] = ComplexD(re: h.re, im: -h.im)
            }
        }

        // 6. IFFT to get real minimum-phase impulse response h_min[n]
        FFT.transform(&fullSpectrum, inverse: true)
        return fullSpectrum.map { $0.re }
    }

    /// Designs a minimum-phase FIR filter from target residual magnitude curve (dB)
    public static func designFir(
        freqs: [Double],
        residualDb: [Double],
        fs: Double,
        nTaps: Int = defaultTaps
    ) -> [Double] {
        var nFft = 64
        while nFft < max(nTaps * 2, 8192) {
            nFft <<= 1
        }
        let halfN = nFft / 2
        let nyquist = 0.5 * fs
        let freqBinStep = nyquist / Double(halfN)

        // Linear FFT bins: 0 Hz to Nyquist
        var fBins = [Double](repeating: 0.0, count: halfN + 1)
        for k in 0...halfN {
            fBins[k] = Double(k) * freqBinStep
        }

        // Interpolate target dB curve onto linear frequency bins
        let interpDb = LogGrid.interp(x: fBins, xp: freqs, yp: residualDb)
        var magLin = [Double](repeating: 1.0, count: halfN + 1)

        for k in 0...halfN {
            let clippedDb = min(max(interpDb[k], -gainClipDb), gainClipDb)
            magLin[k] = pow(10.0, clippedDb / 20.0)
        }

        // DC stabilization: frequencies below 15 Hz match 20 Hz magnitude
        var idx20 = 0
        var minDiff = Double.infinity
        for (idx, f) in fBins.enumerated() {
            let d = abs(f - 20.0)
            if d < minDiff {
                minDiff = d
                idx20 = idx
            }
        }
        let ref20Mag = magLin[idx20]
        for k in 0...halfN where fBins[k] < 15.0 {
            magLin[k] = ref20Mag
        }

        // High frequency roll-off near Nyquist (> 0.90 Nyquist)
        let rollStart = 0.90 * nyquist
        let rollSpan = max(0.10 * nyquist, 1.0)
        for k in 0...halfN where fBins[k] > rollStart {
            let t = (fBins[k] - rollStart) / rollSpan
            let factor = min(max(1.0 - 0.85 * t, 0.08), 1.0)
            magLin[k] *= factor
        }

        var ir = minPhaseFromMagnitude(magLin: magLin, nFft: nFft)

        // Truncate to nTaps
        if ir.count > nTaps {
            ir = Array(ir.prefix(nTaps))
        } else if ir.count < nTaps {
            ir.append(contentsOf: [Double](repeating: 0.0, count: nTaps - ir.count))
        }

        // Apply short tail fade-out (last 64 taps or nTaps / 8)
        let fade = min(64, nTaps / 8)
        if fade > 1 {
            for i in 0..<fade {
                let idx = nTaps - fade + i
                let t = Double(fade - 1 - i) / Double(fade - 1)
                ir[idx] *= t
            }
        }

        // Normalize peak if necessary
        var maxPeak = 0.0
        for val in ir {
            let a = abs(val)
            if a > maxPeak { maxPeak = a }
        }
        if maxPeak > 4.0 {
            let scale = 4.0 / maxPeak
            for i in 0..<ir.count { ir[i] *= scale }
        }

        return ir
    }

    /// Evaluates frequency response of the FIR filter (dB) at given frequencies
    public static func firResponseDb(freqs: [Double], ir: [Double], fs: Double) -> [Double] {
        var nFft = 4096
        while nFft < max(ir.count * 2, 4096) {
            nFft <<= 1
        }
        let halfN = nFft / 2
        var buffer = [ComplexD](repeating: ComplexD(re: 0.0), count: nFft)
        for i in 0..<ir.count {
            buffer[i] = ComplexD(re: ir[i], im: 0.0)
        }

        FFT.transform(&buffer, inverse: false)

        var fBins = [Double](repeating: 0.0, count: halfN + 1)
        var binMagDb = [Double](repeating: 0.0, count: halfN + 1)
        let binStep = (fs * 0.5) / Double(halfN)

        for k in 0...halfN {
            fBins[k] = Double(k) * binStep
            let mag = buffer[k].magnitude
            binMagDb[k] = 20.0 * log10(max(mag, 1e-12))
        }

        return LogGrid.interp(x: freqs, xp: fBins, yp: binMagDb)
    }
}
