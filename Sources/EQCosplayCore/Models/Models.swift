import Foundation

public enum FilterType: String, Codable, CaseIterable, Sendable {
    case peaking = "Peaking"
    case lowshelf = "Lowshelf"
    case highshelf = "Highshelf"

    public var displayName: String {
        switch self {
        case .peaking: return "Peak"
        case .lowshelf: return "Low Shelf"
        case .highshelf: return "High Shelf"
        }
    }
}

public struct PEQBand: Identifiable, Codable, Equatable, Hashable, Sendable {
    public var id: UUID
    public var type: FilterType
    public var frequency: Double
    public var gain: Double
    public var q: Double

    public init(id: UUID = UUID(), type: FilterType, frequency: Double, gain: Double, q: Double) {
        self.id = id
        self.type = type
        self.frequency = frequency
        self.gain = gain
        self.q = q
    }
}

public struct HeadphoneEntry: Identifiable, Codable, Hashable, Sendable {
    public var id: String { relativePath }
    public var name: String
    public var form: String
    public var rig: String
    public var provider: String
    public var relativePath: String
    public var displayName: String {
        if provider.isEmpty {
            return name
        }
        return "\(name) (\(provider))"
    }

    public init(name: String, form: String, rig: String, provider: String, relativePath: String) {
        self.name = name
        self.form = form
        self.rig = rig
        self.provider = provider
        self.relativePath = relativePath
    }
}

public struct CriticalBandStat: Codable, Equatable, Hashable, Sendable {
    public var name: String
    public var fLo: Double
    public var fHi: Double
    public var maxAbs: Double
    public var ptp: Double
    public var rms: Double
    public var isLarge: Bool

    public init(name: String, fLo: Double, fHi: Double, maxAbs: Double, ptp: Double, rms: Double, isLarge: Bool) {
        self.name = name
        self.fLo = fLo
        self.fHi = fHi
        self.maxAbs = maxAbs
        self.ptp = ptp
        self.rms = rms
        self.isLarge = isLarge
    }
}

public struct CorrectionResult: Sendable {
    public var peqBands: [PEQBand]
    public var peqRmse: Double
    public var peqRmseSmooth: Double
    public var useFir: Bool
    public var firIr: [Double]?
    public var firTaps: Int
    public var firRmse: Double
    public var combinedRmse: Double
    public var responsePeak: Double
    public var responseValley: Double
    public var levelOffsetDb: Double
    public var needsFir: Bool
    public var criticalStats: [CriticalBandStat]
    public var gridFreqs: [Double]
    public var sourceCurve: [Double]
    public var targetCurve: [Double]
    public var simulatedCurve: [Double]
    public var peqResponse: [Double]

    public init(
        peqBands: [PEQBand],
        peqRmse: Double,
        peqRmseSmooth: Double,
        useFir: Bool,
        firIr: [Double]?,
        firTaps: Int,
        firRmse: Double,
        combinedRmse: Double,
        responsePeak: Double,
        responseValley: Double,
        levelOffsetDb: Double,
        needsFir: Bool,
        criticalStats: [CriticalBandStat],
        gridFreqs: [Double],
        sourceCurve: [Double],
        targetCurve: [Double],
        simulatedCurve: [Double],
        peqResponse: [Double]
    ) {
        self.peqBands = peqBands
        self.peqRmse = peqRmse
        self.peqRmseSmooth = peqRmseSmooth
        self.useFir = useFir
        self.firIr = firIr
        self.firTaps = firTaps
        self.firRmse = firRmse
        self.combinedRmse = combinedRmse
        self.responsePeak = responsePeak
        self.responseValley = responseValley
        self.levelOffsetDb = levelOffsetDb
        self.needsFir = needsFir
        self.criticalStats = criticalStats
        self.gridFreqs = gridFreqs
        self.sourceCurve = sourceCurve
        self.targetCurve = targetCurve
        self.simulatedCurve = simulatedCurve
        self.peqResponse = peqResponse
    }
}

public enum PreampMode: Codable, Equatable, Hashable, Sendable {
    case safe
    case moderate
    case custom(Double)
    case none

    public func calculateGain(peak: Double) -> Double {
        if peak <= 0.0 { return 0.0 }
        switch self {
        case .safe:
            return -(peak + 0.2)
        case .moderate:
            return -(peak / 2.0)
        case .custom(let val):
            return val
        case .none:
            return 0.0
        }
    }
}

public enum SupportedSampleRate: Int, CaseIterable, Identifiable, Sendable {
    case r44100 = 44100
    case r48000 = 48000
    case r88200 = 88200
    case r96000 = 96000
    case r192000 = 192000

    public var id: Int { rawValue }
    public var label: String {
        switch self {
        case .r44100: return "44.1 kHz"
        case .r48000: return "48.0 kHz"
        case .r88200: return "88.2 kHz"
        case .r96000: return "96.0 kHz"
        case .r192000: return "192.0 kHz"
        }
    }
}

public struct AudioDevice: Identifiable, Equatable, Hashable, Sendable {
    public var id: UInt32
    public var name: String
    public var uid: String
    public var isDefault: Bool

    public init(id: UInt32, name: String, uid: String, isDefault: Bool) {
        self.id = id
        self.name = name
        self.uid = uid
        self.isDefault = isDefault
    }
}

public struct PresetInfo: Identifiable, Equatable, Hashable, Sendable {
    public var id: String { path.path }
    public var name: String
    public var path: URL
    public var sourceName: String
    public var targetName: String
    public var hasFir: Bool
    public var metrics: [String: Double]
    public var modifiedDate: Date

    public init(
        name: String,
        path: URL,
        sourceName: String,
        targetName: String,
        hasFir: Bool,
        metrics: [String: Double],
        modifiedDate: Date
    ) {
        self.name = name
        self.path = path
        self.sourceName = sourceName
        self.targetName = targetName
        self.hasFir = hasFir
        self.metrics = metrics
        self.modifiedDate = modifiedDate
    }
}
