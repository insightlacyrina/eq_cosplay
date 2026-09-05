import Foundation

public enum WavWriter {
    /// Writes mono 32-bit float IEEE PCM WAV file compliant with standard RIFF WAVE specification
    /// (18-byte fmt chunk + fact chunk for WAVE_FORMAT_IEEE_FLOAT).
    public static func writeFloat32Wav(url: URL, samples: [Float], sampleRate: Int) throws {
        let parentDir = url.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: parentDir, withIntermediateDirectories: true)

        var data = Data()
        let numChannels: UInt16 = 1
        let bitsPerSample: UInt16 = 32
        let bytesPerSample: UInt16 = 4
        let blockAlign: UInt16 = numChannels * bytesPerSample
        let byteRate: UInt32 = UInt32(sampleRate) * UInt32(blockAlign)
        let dataChunkSize: UInt32 = UInt32(samples.count) * UInt32(bytesPerSample)

        // RIFF chunk size = 4 ("WAVE") + (8 + 18) [fmt] + (8 + 4) [fact] + (8 + dataChunkSize) [data]
        let riffChunkSize: UInt32 = 4 + 26 + 12 + (8 + dataChunkSize)

        // 1. RIFF Header
        data.append(contentsOf: "RIFF".utf8)
        var riffSizeLE = riffChunkSize.littleEndian
        data.append(Data(bytes: &riffSizeLE, count: 4))
        data.append(contentsOf: "WAVE".utf8)

        // 2. "fmt " Subchunk (18 bytes for IEEE Float, format code 3)
        data.append(contentsOf: "fmt ".utf8)
        var fmtChunkSizeLE: UInt32 = UInt32(18).littleEndian
        data.append(Data(bytes: &fmtChunkSizeLE, count: 4))

        var formatCodeLE: UInt16 = UInt16(3).littleEndian // IEEE Float
        data.append(Data(bytes: &formatCodeLE, count: 2))

        var channelsLE = numChannels.littleEndian
        data.append(Data(bytes: &channelsLE, count: 2))

        var srLE = UInt32(sampleRate).littleEndian
        data.append(Data(bytes: &srLE, count: 4))

        var byteRateLE = byteRate.littleEndian
        data.append(Data(bytes: &byteRateLE, count: 4))

        var blockAlignLE = blockAlign.littleEndian
        data.append(Data(bytes: &blockAlignLE, count: 2))

        var bitsLE = bitsPerSample.littleEndian
        data.append(Data(bytes: &bitsLE, count: 2))

        var cbSizeLE: UInt16 = UInt16(0).littleEndian
        data.append(Data(bytes: &cbSizeLE, count: 2))

        // 3. "fact" Subchunk (required for IEEE float)
        data.append(contentsOf: "fact".utf8)
        var factChunkSizeLE: UInt32 = UInt32(4).littleEndian
        data.append(Data(bytes: &factChunkSizeLE, count: 4))

        var sampleCountLE = UInt32(samples.count).littleEndian
        data.append(Data(bytes: &sampleCountLE, count: 4))

        // 4. "data" Subchunk
        data.append(contentsOf: "data".utf8)
        var dataSizeLE = dataChunkSize.littleEndian
        data.append(Data(bytes: &dataSizeLE, count: 4))

        // 5. Sample Data
        samples.withUnsafeBufferPointer { buffer in
            guard let baseAddress = buffer.baseAddress else { return }
            data.append(UnsafeRawPointer(baseAddress).assumingMemoryBound(to: UInt8.self), count: Int(dataChunkSize))
        }

        try data.write(to: url, options: .atomic)
    }
}
