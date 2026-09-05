import Foundation

public enum WavWriter {
    /// Writes mono 32-bit float IEEE PCM WAV file
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
        let riffChunkSize: UInt32 = 36 + dataChunkSize

        // RIFF Header
        data.append(contentsOf: "RIFF".utf8)
        var riffSizeLE = riffChunkSize.littleEndian
        data.append(Data(bytes: &riffSizeLE, count: 4))
        data.append(contentsOf: "WAVE".utf8)

        // "fmt " Subchunk (Standard 16-byte format chunk, format code 3 = IEEE Float)
        data.append(contentsOf: "fmt ".utf8)
        var fmtChunkSizeLE: UInt32 = UInt32(16).littleEndian
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

        // "data" Subchunk
        data.append(contentsOf: "data".utf8)
        var dataSizeLE = dataChunkSize.littleEndian
        data.append(Data(bytes: &dataSizeLE, count: 4))

        // Sample Data
        samples.withUnsafeBufferPointer { buffer in
            guard let baseAddress = buffer.baseAddress else { return }
            data.append(UnsafeRawPointer(baseAddress).assumingMemoryBound(to: UInt8.self), count: Int(dataChunkSize))
        }

        try data.write(to: url, options: .atomic)
    }
}
