import Foundation
import EQCosplayCore

var totalTests = 0
var passedTests = 0

func assertTrue(_ condition: Bool, _ message: String, file: String = #file, line: Int = #line) {
    totalTests += 1
    if condition {
        passedTests += 1
        print("  \u{001B}[32m✓\u{001B}[0m \(message)")
    } else {
        print("  \u{001B}[31m✗ FAIL:\u{001B}[0m \(message) [\(file):\(line)]")
    }
}

func assertEqual<T: Equatable>(_ a: T, _ b: T, _ message: String, file: String = #file, line: Int = #line) {
    assertTrue(a == b, "\(message) (expected \(b), got \(a))", file: file, line: line)
}

func assertAccuracy(_ a: Double, _ b: Double, accuracy: Double, _ message: String, file: String = #file, line: Int = #line) {
    let diff = abs(a - b)
    assertTrue(diff <= accuracy, "\(message) (diff \(diff) <= \(accuracy))", file: file, line: line)
}

print("\n=======================================================")
print("           EQ Cosplay Swift Test Suite")
print("=======================================================\n")

let fs = 48000.0

// Test Group 1: Biquad Math
print("Testing Biquad Filters...")
do {
    let f0 = 1000.0
    let targetGain = 6.0
    let q = 1.414
    let resp = Biquad.responseDb(type: .peaking, f0: f0, gainDb: targetGain, q: q, freqs: [f0], fs: fs)
    assertAccuracy(resp[0], targetGain, accuracy: 0.1, "Peaking response at f0 matches gain")

    let lowResp = Biquad.responseDb(type: .lowshelf, f0: 100.0, gainDb: 5.0, q: 0.707, freqs: [20.0], fs: fs)
    assertAccuracy(lowResp[0], 5.0, accuracy: 0.5, "Lowshelf response at 20Hz matches gain")

    let highResp = Biquad.responseDb(type: .highshelf, f0: 8000.0, gainDb: -4.0, q: 0.707, freqs: [18000.0], fs: fs)
    assertAccuracy(highResp[0], -4.0, accuracy: 0.5, "Highshelf response at 18kHz matches gain")

    let band1 = PEQBand(type: .peaking, frequency: 1000.0, gain: 3.0, q: 1.0)
    let band2 = PEQBand(type: .peaking, frequency: 5000.0, gain: -3.0, q: 1.0)
    let sumResp = Biquad.peqResponseDb(bands: [band1, band2], freqs: [1000.0, 5000.0], fs: fs)
    assertTrue(sumResp[0] > 2.0 && sumResp[1] < -2.0, "PEQ chain sum response correct")
}

// Test Group 2: LogGrid and Smoothing
print("\nTesting LogGrid & Smoothing...")
do {
    let freqs = LogGrid.makeLogFreqs(numPoints: 512, fmin: 20.0, fmax: 20000.0)
    assertEqual(freqs.count, 512, "LogGrid has 512 points")
    assertAccuracy(freqs.first!, 20.0, accuracy: 1e-4, "LogGrid begins at 20 Hz")
    assertAccuracy(freqs.last!, 20000.0, accuracy: 1e-4, "LogGrid ends at 20000 Hz")

    var monotonic = true
    for i in 1..<freqs.count {
        if freqs[i] <= freqs[i - 1] { monotonic = false; break }
    }
    assertTrue(monotonic, "LogGrid strictly monotonic")

    let noisy = freqs.map { sin(log10($0) * 8.0) * 4.0 + 3.0 }
    let (aligned, offset) = Smoothing.alignDeltaLevel(freqs: freqs, deltaDb: noisy)
    assertTrue(offset > 0.0, "Level alignment offset non-zero")
    let smoothed = Smoothing.smoothCurveLogF(freqs: freqs, curve: aligned, octaves: 1.0 / 6.0)
    assertEqual(smoothed.count, 512, "Smoothed curve retains length")
}

// Test Group 3: Optimizer
print("\nTesting 10-Band PEQ Optimizer...")
do {
    let freqs = LogGrid.makeLogFreqs(numPoints: 512)
    var delta = [Double](repeating: 0.0, count: 512)
    for i in 0..<512 {
        let f = freqs[i]
        if f < 200.0 {
            delta[i] = 4.0 * (1.0 - f / 200.0)
        } else if f > 2000.0 && f < 5000.0 {
            let mid = 3500.0
            let w = (f - mid) / 800.0
            delta[i] = -3.5 * exp(-0.5 * w * w)
        }
    }

    let initial = PEQOptimizer.initializeBands(freqs: freqs, delta: delta, fs: fs)
    assertEqual(initial.count, 10, "Initializer returns 10 bands")

    let (fitted, rmse) = PEQOptimizer.optimizeBands(freqs: freqs, delta: delta, initialBands: initial, fs: fs, maxIterations: 30)
    assertEqual(fitted.count, 10, "Fitted bands count equals 10")
    assertTrue(rmse < 2.0, "Fitted RMSE under 2.0 dB (actual: \(String(format: "%.2f", rmse)) dB)")
}

// Test Group 4: FFT & Minimum-Phase FIR
print("\nTesting FFT & FIR Synthesis...")
do {
    let n = 256
    var original = [ComplexD](repeating: ComplexD(re: 0.0), count: n)
    for i in 0..<n {
        original[i] = ComplexD(re: sin(Double(i) * 0.1) * 3.0, im: cos(Double(i) * 0.05))
    }

    var transformed = original
    FFT.transform(&transformed, inverse: false)
    var inverted = transformed
    FFT.transform(&inverted, inverse: true)

    var fftAccurate = true
    for i in 0..<n {
        if abs(inverted[i].re - original[i].re) > 1e-5 || abs(inverted[i].im - original[i].im) > 1e-5 {
            fftAccurate = false
            break
        }
    }
    assertTrue(fftAccurate, "IFFT(FFT(x)) == x roundtrip identity")

    let freqs = LogGrid.makeLogFreqs(numPoints: 512)
    let residual = freqs.map { sin(log10($0) * 8.0) * 2.0 }
    let ir = FIRDesigner.designFir(freqs: freqs, residualDb: residual, fs: fs, nTaps: 1024)
    assertEqual(ir.count, 1024, "FIR filter length is 1024 taps")

    let earlyEnergy = ir.prefix(64).reduce(0.0) { $0 + $1 * $1 }
    let tailEnergy = ir.suffix(64).reduce(0.0) { $0 + $1 * $1 }
    assertTrue(earlyEnergy > tailEnergy, "Minimum phase causality: early energy > tail energy")

    // Test WAV output
    let tempUrl = FileManager.default.temporaryDirectory.appendingPathComponent("test_fir_\(UUID().uuidString).wav")
    let floatSamples = ir.map { Float($0) }
    try WavWriter.writeFloat32Wav(url: tempUrl, samples: floatSamples, sampleRate: 48000)
    assertTrue(FileManager.default.fileExists(atPath: tempUrl.path), "WAV file written to disk")

    let attr = try FileManager.default.attributesOfItem(atPath: tempUrl.path)
    let fileSize = (attr[.size] as? NSNumber)?.intValue ?? 0
    assertEqual(fileSize, 44 + 1024 * 4, "WAV file size matches exact 44-byte RIFF header + float payload")
    try? FileManager.default.removeItem(at: tempUrl)
}

// Test Group 5: AutoEq Index Parser & CamillaDSP YAML
print("\nTesting IndexParser & CamillaDSP YAML...")
do {
    let mockIndex = """
    # Results
    | [Sony WH-1000XM4](./oratory1990/over-ear/Sony%20WH-1000XM4) | [over-ear](./oratory1990/over-ear) | oratory1990 |
    | [AKG Q701](./innerfidelity/innerfidelity_harman_over-ear_2018/AKG%20Q701) | [over-ear](./innerfidelity) | innerfidelity |
    """
    let parsed = IndexParser.parseAutoEqIndex(rawText: mockIndex)
    assertTrue(parsed.keys.contains("sony wh-1000xm4"), "Parsed Sony WH-1000XM4 entry")
    assertTrue(parsed.keys.contains("akg q701"), "Parsed AKG Q701 entry")

    let band = PEQBand(type: .peaking, frequency: 1000.0, gain: 3.5, q: 1.4)
    let yaml = CamillaDSPConfig.generateYAML(
        bands: [band],
        outputDeviceName: "External Headphones",
        sampleRate: 48000,
        preampGain: -3.5,
        metrics: ["peq_rmse": 1.25]
    )
    assertTrue(yaml.contains("peq_01:"), "YAML contains peq_01 filter")
    assertTrue(yaml.contains("preamp_gain:"), "YAML contains preamp_gain filter")
    assertTrue(yaml.contains("External Headphones"), "YAML contains target playback device")
    assertTrue(yaml.contains("# eq_cosplay_metrics:"), "YAML contains embedded metrics comment")
}

// Test Group 6: AutoEq CSV Fetcher & Provider Fallback
print("\nTesting CSVFetcher & Provider Fallback...")
do {
    let crinacleEntry = HeadphoneEntry(
        name: "Sony WH-1000XM4",
        form: "over-ear",
        rig: "crinacle",
        provider: "crinacle",
        relativePath: "crinacle/GRAS 43AG-7 over-ear/Sony WH-1000XM4"
    )
    let candidates = CSVFetcher.providerCandidates(for: crinacleEntry)
    assertTrue(candidates.count >= 2, "Sony WH-1000XM4 has provider candidates (found \(candidates.count))")
    assertTrue(candidates.contains(where: { $0.provider.lowercased().contains("oratory") }), "Candidates include oratory1990 fallback")

    let semaphore = DispatchSemaphore(value: 0)
    var fetchSuccess = false
    var returnedFreqs = 0
    var usedProvider = ""
    Task {
        do {
            let res = try await CSVFetcher.fetchCSVWithDetails(for: crinacleEntry)
            fetchSuccess = !res.freqs.isEmpty
            returnedFreqs = res.freqs.count
            usedProvider = res.usedEntry.provider
        } catch {
            print("Fetch failed: \(error)")
        }
        semaphore.signal()
    }
    _ = semaphore.wait(timeout: .now() + 15.0)

    assertTrue(fetchSuccess, "Downloaded CSV for Sony WH-1000XM4 with fallback (used \(usedProvider), \(returnedFreqs) points)")
}

print("\n-------------------------------------------------------")
if passedTests == totalTests {
    print("\u{001B}[32mAll \(totalTests) tests passed successfully!\u{001B}[0m")
    exit(0)
} else {
    print("\u{001B}[31m\(totalTests - passedTests) of \(totalTests) tests failed.\u{001B}[0m")
    exit(1)
}
