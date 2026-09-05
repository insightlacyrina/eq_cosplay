import Foundation

public final class CamillaProcess: @unchecked Sendable {
    public static let shared = CamillaProcess()

    private var currentProcess: Process?
    private var logFileHandle: FileHandle?
    public private(set) var activeConfigPath: URL?
    public var onLogMessage: ((String) -> Void)?

    public var isRunning: Bool {
        guard let p = currentProcess else { return false }
        return p.isRunning
    }

    private init() {}

    public static func findExecutable() -> URL? {
        // 1. Check App bundle
        if let bundleUrl = Bundle.main.url(forResource: "camilladsp", withExtension: nil) {
            return bundleUrl
        }

        // 2. Candidate paths
        let home = FileManager.default.homeDirectoryForCurrentUser
        let candidates = [
            URL(fileURLWithPath: "/Users/zhuyongfei/Desktop/eq_cosplay/camilladsp"),
            URL(fileURLWithPath: "/Users/zhuyongfei/Desktop/eq_cosplay_swift/camilladsp"),
            URL(fileURLWithPath: "/opt/homebrew/bin/camilladsp"),
            URL(fileURLWithPath: "/usr/local/bin/camilladsp"),
            home.appendingPathComponent("Library/Application Support/EQ Cosplay/bin/camilladsp"),
            home.appendingPathComponent(".cargo/bin/camilladsp")
        ]

        for c in candidates {
            if FileManager.default.isExecutableFile(atPath: c.path) {
                return c
            }
        }

        // 3. which camilladsp
        let whichProcess = Process()
        whichProcess.executableURL = URL(fileURLWithPath: "/usr/bin/which")
        whichProcess.arguments = ["camilladsp"]
        let pipe = Pipe()
        whichProcess.standardOutput = pipe
        try? whichProcess.run()
        whichProcess.waitUntilExit()

        if whichProcess.terminationStatus == 0 {
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            if let output = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines),
               !output.isEmpty && FileManager.default.isExecutableFile(atPath: output) {
                return URL(fileURLWithPath: output)
            }
        }

        return nil
    }

    public static func stopExistingInstances() {
        let pkill = Process()
        pkill.executableURL = URL(fileURLWithPath: "/usr/bin/pkill")
        pkill.arguments = ["-9", "-x", "camilladsp"]
        try? pkill.run()
        pkill.waitUntilExit()
    }

    public func start(configPath: URL, debug: Bool = false) throws {
        stop()
        Self.stopExistingInstances()

        guard let exe = Self.findExecutable() else {
            throw NSError(
                domain: "CamillaProcess",
                code: 404,
                userInfo: [NSLocalizedDescriptionKey: "CamillaDSP executable not found. Please install CamillaDSP."]
            )
        }

        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let logsDir = appSupport.appendingPathComponent("EQ Cosplay/logs", isDirectory: true)
        try? FileManager.default.createDirectory(at: logsDir, withIntermediateDirectories: true)

        let formatter = DateFormatter()
        formatter.dateFormat = "yyyyMMdd_HHmmss"
        let dateStr = formatter.string(from: Date())
        let logFile = logsDir.appendingPathComponent("camilladsp_\(dateStr).log")

        FileManager.default.createFile(atPath: logFile.path, contents: nil)
        let fileHandle = try FileHandle(forWritingTo: logFile)
        self.logFileHandle = fileHandle

        let header = """
        # EQ Cosplay / CamillaDSP log
        # started: \(Date())
        # config:  \(configPath.path)
        # ---\n
        """
        if let headerData = header.data(using: .utf8) {
            fileHandle.write(headerData)
        }

        let process = Process()
        process.executableURL = exe
        process.arguments = [
            "-l", debug ? "debug" : "info",
            configPath.path
        ]

        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe

        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty else { return }
            self?.logFileHandle?.write(data)
            if let text = String(data: data, encoding: .utf8) {
                DispatchQueue.main.async {
                    self?.onLogMessage?(text)
                }
            }
        }

        try process.run()
        self.currentProcess = process
        self.activeConfigPath = configPath
    }

    public func stop() {
        if let p = currentProcess, p.isRunning {
            p.terminate()
            p.waitUntilExit()
        }
        currentProcess = nil
        activeConfigPath = nil
        try? logFileHandle?.close()
        logFileHandle = nil
        Self.stopExistingInstances()
    }
}
