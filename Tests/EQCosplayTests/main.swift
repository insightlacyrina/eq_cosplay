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
    assertEqual(fileSize, 58 + 1024 * 4, "WAV file size matches exact 58-byte standard RIFF header + float payload")
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


// Test Group 7: CoreAudio Physical Device Filtering & WavWriter Format
print("\nTesting CoreAudio Filtering & WavWriter Compliance...")
do {
    assertTrue(CoreAudioService.isVirtualDevice(name: "BlackHole 2ch"), "BlackHole identified as virtual")
    assertTrue(CoreAudioService.isVirtualDevice(name: "Background Music"), "Background Music identified as virtual")
    assertTrue(!CoreAudioService.isVirtualDevice(name: "External Headphones"), "External Headphones identified as physical")
    assertTrue(!CoreAudioService.isVirtualDevice(name: "外置耳机"), "外置耳机 identified as physical")
    assertTrue(!CoreAudioService.isVirtualDevice(name: "MacBook Pro扬声器"), "MacBook Pro扬声器 identified as physical")

    let physical = CoreAudioService.getAudioOutputDevices()
    for dev in physical {
        assertTrue(!CoreAudioService.isVirtualDevice(name: dev.name), "Output device \(dev.name) is physical")
    }

    // WavWriter test
    let testUrl = URL(fileURLWithPath: "/tmp/test_riff.wav")
    let samples: [Float] = [0.1, -0.2, 0.3, -0.4]
    try WavWriter.writeFloat32Wav(url: testUrl, samples: samples, sampleRate: 48000)
    let data = try Data(contentsOf: testUrl)
    // 58 bytes header + 16 bytes payload = 74 bytes total
    assertEqual(data.count, 74, "Wav file has correct IEEE Float header + payload size")

    // PresetsManager preparePresetForLaunch test
    let samplePreset = """
devices:
  samplerate: 48000
  chunksize: 1024
  capture:
    type: CoreAudio
    channels: 2
    device: "BlackHole 2ch"
  playback:
    type: CoreAudio
    channels: 2
    device: "外置耳机"

filters:
"""
    let tmpPresetURL = URL(fileURLWithPath: "/tmp/sample_preset.yml")
    try samplePreset.write(to: tmpPresetURL, atomically: true, encoding: .utf8)
    let launchedURL = try PresetsManager.preparePresetForLaunch(presetURL: tmpPresetURL, outputDeviceName: "MacBook Pro扬声器")
    let launchedContent = try String(contentsOf: launchedURL, encoding: .utf8)
    assertTrue(launchedContent.contains("device: \"MacBook Pro扬声器\""), "Preset updated to target MacBook Pro扬声器")

    // MARK: - Testing YAML Config Parsing & PresetsManager
    print("\nTesting YAML Parsing, PresetsManager & FIR Toggle...")
    let fullYaml = """
# eq_cosplay_metrics: {"peq_rmse":0.82,"combined_rmse":0.19,"response_peak":-3.5}
devices:
  samplerate: 44100
  chunksize: 1024
  capture:
    type: CoreAudio
    channels: 2
    device: "BlackHole 2ch"
  playback:
    type: CoreAudio
    channels: 2
    device: "Built-in Output"

filters:
  preamp_gain:
    type: Gain
    parameters:
      gain: -4.2
  peq_01:
    type: Biquad
    parameters:
      type: Peaking
      freq: 120.0
      q: 1.41
      gain: 2.5
  peq_02:
    type: Biquad
    parameters:
      type: Lowshelf
      freq: 80.0
      q: 0.707
      gain: -1.8
  fir_corr:
    type: Conv
    parameters:
      type: File
      filename: "/tmp/sample_fir.wav"
"""
    let parsed = CamillaDSPConfig.parseYAML(fullYaml)
    assertEqual(parsed.bands.count, 2, "Parsed 2 PEQ bands from YAML")
    assertEqual(parsed.sampleRate, 44100, "Parsed sampleRate 44100")
    assertAccuracy(parsed.preampGain, -4.2, accuracy: 0.01, "Parsed preamp gain")
    assertEqual(parsed.firLeftPath, "/tmp/sample_fir.wav", "Parsed FIR filename")
    assertEqual(parsed.metrics["peq_rmse"], 0.82, "Parsed embedded peq_rmse")
    assertEqual(parsed.metrics["combined_rmse"], 0.19, "Parsed embedded combined_rmse")

    // Test CorrectionEngine.createResultFromPreset FIR toggle behavior
    let dummyBands = [PEQBand(type: .peaking, frequency: 1000.0, gain: 3.0, q: 1.0)]
    let dummyIr = [Double](repeating: 0.01, count: 64)
    let noFirResult = CorrectionEngine.createResultFromPreset(bands: dummyBands, firIr: dummyIr, metrics: [:], fs: 48000, useFir: false)
    let withFirResult = CorrectionEngine.createResultFromPreset(bands: dummyBands, firIr: dummyIr, metrics: [:], fs: 48000, useFir: true)
    assertTrue(noFirResult.simulatedCurve[256] != withFirResult.simulatedCurve[256], "FIR toggle changes simulated frequency response")
    assertEqual(noFirResult.peqBands.count, 1, "Simulated result has 1 band")

    // Test PresetsManager listPresets discovery
    let presets = PresetsManager.listPresets()
    assertTrue(!presets.isEmpty, "Found bundled/saved presets (count: \(presets.count))")

    // Test Group 9: New Machine Deployment & Dependency Resolution
    print("\nTesting New Machine Deployment & Dependency Helpers...")
    let binDir = CamillaProcess.getBinDirectory()
    assertTrue(FileManager.default.fileExists(atPath: binDir.path), "CamillaProcess bin directory exists")
    let logsDir = CamillaProcess.getLogsDirectory()
    assertTrue(FileManager.default.fileExists(atPath: logsDir.path), "CamillaProcess logs directory exists")

    // Test dynamic WAV path resolution when preset contains foreign absolute paths
    let foreignPresetContent = """
devices:
  samplerate: 48000
  chunksize: 1024
  capture:
    type: CoreAudio
    channels: 2
    device: "BlackHole 2ch"
  playback:
    type: CoreAudio
    channels: 2
    device: "Speakers"
filters:
  fir_left:
    type: Conv
    parameters:
      type: File
      filename: "/Users/foreign_user/Desktop/old_path/test_portability_fir_left.wav"
"""
    let foreignDir = FileManager.default.temporaryDirectory.appendingPathComponent("test_foreign_preset_\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: foreignDir, withIntermediateDirectories: true)
    let foreignYamlURL = foreignDir.appendingPathComponent("test_portability.yml")
    let localWavURL = foreignDir.appendingPathComponent("test_portability_fir_left.wav")
    try foreignPresetContent.write(to: foreignYamlURL, atomically: true, encoding: .utf8)
    try "RIFFdummy".write(to: localWavURL, atomically: true, encoding: .utf8)

    let preparedForeignURL = try PresetsManager.preparePresetForLaunch(presetURL: foreignYamlURL, outputDeviceName: "Target Headphones")
    let preparedForeignContent = try String(contentsOf: preparedForeignURL, encoding: .utf8)
    assertTrue(preparedForeignContent.contains("device: \"Target Headphones\""), "Target output device replaced")
    assertTrue(preparedForeignContent.contains(localWavURL.path), "Foreign FIR WAV path dynamically updated to local path")
    assertTrue(!preparedForeignContent.contains("foreign_user"), "Foreign path stripped cleanly")
    try? FileManager.default.removeItem(at: foreignDir)
}

// Test Group 10: XM4 → K3003 parity with the Python sibling
print("\nTesting XM4 → K3003 correction (Python sibling parity)...")
do {
    let cacheDir = CSVFetcher.getCacheDir()
    let srcURL = cacheDir.appendingPathComponent("Sony_WH-1000XM4_oratory1990.csv")
    let tgtURL = cacheDir.appendingPathComponent("AKG_K3003_oratory1990.csv")

    func loadCSV(_ url: URL) -> (freqs: [Double], mags: [Double])? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        return CSVFetcher.parseCSVData(data)
    }

    if let src = loadCSV(srcURL), let tgt = loadCSV(tgtURL) {
        let result = CorrectionEngine.calculateCorrection(
            sourceFreqs: src.freqs,
            sourceMags: src.mags,
            targetFreqs: tgt.freqs,
            targetMags: tgt.mags,
            fs: fs
        )
        print("    peq_rmse=\(String(format: "%.4f", result.peqRmse)) combined_rmse=\(String(format: "%.4f", result.combinedRmse)) level_offset=\(String(format: "%.3f", result.levelOffsetDb))")

        assertTrue(result.useFir, "XM4→K3003 triggers FIR residual")
        // Python sibling: peq_rmse ~1.220, combined RMSE ~0.144 dB on this pair.
        assertTrue(
            result.peqRmse < 1.35,
            "PEQ RMSE near Python 1.22 dB (actual \(String(format: "%.4f", result.peqRmse)))"
        )
        assertTrue(
            result.combinedRmse < 0.15,
            "Combined RMSE near Python 0.144 dB (actual \(String(format: "%.4f", result.combinedRmse)))"
        )

        var sumBias = 0.0
        for i in 0..<result.simulatedCurve.count {
            sumBias += result.simulatedCurve[i] - result.targetCurve[i]
        }
        let meanBias = sumBias / Double(max(result.simulatedCurve.count, 1))
        assertTrue(
            abs(meanBias) < 0.05,
            "Simulated vs aligned target has no systematic offset (mean \(String(format: "%.4f", meanBias)) dB)"
        )
    } else {
        print("    [skip] cached XM4/K3003 CSVs not found")
    }
}

// Test Group 11: Preset Headphone Provider Parsing & Plot Modes
print("\nTesting Preset Provider Parsing & Plot Display Modes...")
do {
    // 1. parseModelAndProvider
    let (m1, p1) = PresetsManager.parseModelAndProvider(rawString: "Sony_WH-1000XM4_oratory1990")
    assertEqual(m1, "Sony WH-1000XM4", "Parsed model name from underscore filename")
    assertEqual(p1, "oratory1990", "Parsed provider from underscore filename")

    let (m2, p2) = PresetsManager.parseModelAndProvider(rawString: "Audio-Technica_ATH-M50xBT2_Rtings")
    assertEqual(m2, "Audio-Technica ATH-M50xBT2", "Parsed hyphenated model name")
    assertEqual(p2, "Rtings", "Parsed capitalized provider")

    let (m3, p3) = PresetsManager.parseModelAndProvider(rawString: "Sony WH-1000XM4 (oratory1990)")
    assertEqual(m3, "Sony WH-1000XM4", "Parsed model name from parentheses")
    assertEqual(p3, "oratory1990", "Parsed provider from parentheses")

    let (m4, p4) = PresetsManager.parseModelAndProvider(rawString: "Custom_Headphone")
    assertEqual(m4, "Custom Headphone", "Parsed model name without provider")
    assertEqual(p4, "", "Empty provider when none present")

    // 2. HeadphoneEntry.displayName
    let e1 = HeadphoneEntry(name: "Sony WH-1000XM4", form: "", rig: "", provider: "oratory1990", relativePath: "")
    assertEqual(e1.displayName, "Sony WH-1000XM4 (oratory1990)", "displayName encloses provider in parentheses")

    let e2 = HeadphoneEntry(name: "Sony WH-1000XM4 (oratory1990)", form: "", rig: "", provider: "oratory1990", relativePath: "")
    assertEqual(e2.displayName, "Sony WH-1000XM4 (oratory1990)", "displayName avoids double parentheses")

    let e3 = HeadphoneEntry(name: "Sennheiser HD 600", form: "", rig: "", provider: "", relativePath: "")
    assertEqual(e3.displayName, "Sennheiser HD 600", "displayName omits empty parentheses")
    assertTrue(!e3.displayName.contains("()"), "displayName contains no empty ()")

    // 3. Preset discovery model/provider separation
    let presets = PresetsManager.listPresets()
    if let xm4Preset = presets.first(where: { $0.path.lastPathComponent.contains("WH-1000XM4") && $0.path.lastPathComponent.contains("Q701") }) {
        assertEqual(xm4Preset.sourceModel, "Sony WH-1000XM4", "PresetInfo extracted source model cleanly")
        assertEqual(xm4Preset.sourceProvider, "oratory1990", "PresetInfo extracted source provider cleanly")
        assertEqual(xm4Preset.targetModel, "AKG Q701", "PresetInfo extracted target model cleanly")
        assertEqual(xm4Preset.targetProvider, "oratory1990", "PresetInfo extracted target provider cleanly")
        assertTrue(!xm4Preset.sourceName.contains("()"), "Preset sourceName has no empty ()")
    }

    // 4. CorrectionResult compensationCurve
    let dummyBands = [PEQBand(type: .peaking, frequency: 1000.0, gain: 3.0, q: 1.0)]
    let dummyRes = CorrectionEngine.createResultFromPreset(bands: dummyBands, firIr: nil, metrics: [:], fs: 48000, useFir: false)
    assertEqual(dummyRes.compensationCurve.count, 512, "CorrectionResult compensationCurve has 512 points")
}

// Test Group 12: FIR pre-smooth must not move a resolved 9–11 kHz apex
print("\nTesting FIR peak alignment around 8.4–11 kHz...")
do {
    func bandArgMaxIndex(_ freqs: [Double], _ curve: [Double], _ lo: Double, _ hi: Double) -> Int {
        var best = 0
        var bestVal = -Double.infinity
        for i in 0..<freqs.count where freqs[i] >= lo && freqs[i] <= hi {
            if curve[i] > bestVal {
                bestVal = curve[i]
                best = i
            }
        }
        return best
    }

    let freqs = LogGrid.makeLogFreqs(numPoints: 512)
    let iPeak = freqs.enumerated().min(by: { abs($0.element - 9008.0) < abs($1.element - 9008.0) })!.offset
    let iNotch = freqs.enumerated().min(by: { abs($0.element - 9902.0) < abs($1.element - 9902.0) })!.offset
    var residual = [Double](repeating: 0.0, count: freqs.count)
    for i in 0..<freqs.count {
        let peakTerm = log2(freqs[i] / freqs[iPeak]) / 0.02
        let notchTerm = log2(freqs[i] / freqs[iNotch]) / 0.06
        residual[i] = 1.2 * exp(-0.5 * peakTerm * peakTerm) - 6.0 * exp(-0.5 * notchTerm * notchTerm)
    }

    let rawApex = bandArgMaxIndex(freqs, residual, 8400.0, 11000.0)
    assertEqual(rawApex, iPeak, "Synthetic residual apex sits on the 9008 Hz bin")

    let broad = Smoothing.smoothCurveLogF(freqs: freqs, curve: residual, octaves: 1.0 / 12.0)
    let broadApex = bandArgMaxIndex(freqs, broad, 8400.0, 11000.0)
    assertTrue(
        abs(broadApex - iPeak) > 1,
        "1/12 oct smooth moves the 9008 Hz apex by more than one bin (shift \(broadApex - iPeak))"
    )

    let fine = Smoothing.smoothCurveLogF(freqs: freqs, curve: residual, octaves: Smoothing.firSmoothOctaves)
    let fineApex = bandArgMaxIndex(freqs, fine, 8400.0, 11000.0)
    assertEqual(fineApex, iPeak, "1/48 oct smooth keeps the apex on the 9008 Hz bin")

    let ir = FIRDesigner.designFir(freqs: freqs, residualDb: fine, fs: fs, nTaps: 8192)
    let firResp = FIRDesigner.firResponseDb(freqs: freqs, ir: ir, fs: fs)
    let firApex = bandArgMaxIndex(freqs, firResp, 8400.0, 11000.0)
    let freqRatio = max(freqs[firApex], freqs[rawApex]) / min(freqs[firApex], freqs[rawApex])
    assertTrue(freqRatio < 1.02, "FIR apex stays within 2% of the raw residual apex (ratio \(freqRatio))")

    var sumSq = 0.0
    var count = 0
    for i in 0..<freqs.count where freqs[i] >= 8400.0 && freqs[i] <= 11000.0 {
        let err = firResp[i] - residual[i]
        sumSq += err * err
        count += 1
    }
    let bandRms = sqrt(sumSq / Double(max(count, 1)))
    assertTrue(bandRms < 0.15, "FIR matches the raw residual in 8.4–11 kHz (RMS \(String(format: "%.3f", bandRms)) dB)")

    let cacheDir = CSVFetcher.getCacheDir()
    let srcURL = cacheDir.appendingPathComponent("AKG_K3003_(bass_boost_filter)_Innerfidelity.csv")
    let tgtURL = cacheDir.appendingPathComponent("Etymotic_ER4SR_Innerfidelity.csv")
    if let srcData = try? Data(contentsOf: srcURL),
       let tgtData = try? Data(contentsOf: tgtURL),
       let src = CSVFetcher.parseCSVData(srcData),
       let tgt = CSVFetcher.parseCSVData(tgtData) {
        let result = CorrectionEngine.calculateCorrection(
            sourceFreqs: src.freqs,
            sourceMags: src.mags,
            targetFreqs: tgt.freqs,
            targetMags: tgt.mags,
            fs: fs
        )
        let grid = result.gridFreqs
        let targetApex = bandArgMaxIndex(grid, result.targetCurve, 8400.0, 11000.0)
        let simApex = bandArgMaxIndex(grid, result.simulatedCurve, 8400.0, 11000.0)
        print("    K3003→ER4SR target apex \(String(format: "%.0f", grid[targetApex])) Hz, simulated \(String(format: "%.0f", grid[simApex])) Hz")
        assertTrue(
            abs(simApex - targetApex) <= 1,
            "K3003→ER4SR simulated apex is within one bin of the target (target \(String(format: "%.0f", grid[targetApex])) Hz, sim \(String(format: "%.0f", grid[simApex])) Hz)"
        )

        var bandSum = 0.0
        var bandCount = 0
        for i in 0..<grid.count where grid[i] >= 8400.0 && grid[i] <= 11000.0 {
            let err = result.simulatedCurve[i] - result.targetCurve[i]
            bandSum += err * err
            bandCount += 1
        }
        let pairRms = sqrt(bandSum / Double(max(bandCount, 1)))
        assertTrue(
            pairRms < 0.15,
            "K3003→ER4SR 8.4–11 kHz combined RMS under 0.15 dB (actual \(String(format: "%.3f", pairRms)) dB)"
        )
    } else {
        print("    [skip] cached K3003 bass-boost / ER4SR CSVs not found")
    }
}

print("\n-------------------------------------------------------")
if passedTests == totalTests {
    print("\u{001B}[32mAll \(totalTests) tests passed successfully!\u{001B}[0m")
    exit(0)
} else {
    print("\u{001B}[31m\(totalTests - passedTests) of \(totalTests) tests failed.\u{001B}[0m")
    exit(1)
}
