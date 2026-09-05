import Foundation

public final class CamillaProcess: @unchecked Sendable {
    public static let shared = CamillaProcess()

    private var currentProcess: Process?
    private var logFileHandle: FileHandle?
    private var tailTask: Task<Void, Never>?
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
            URL(fileURLWithPath: "/Users/zhuyongfei/Desktop/eq_cosplay_swift/dist/EQ Cosplay.app/Contents/Resources/camilladsp"),
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
        let writeHandle = try FileHandle(forWritingTo: logFile)
        self.logFileHandle = writeHandle

        let header = """
        # EQ Cosplay / CamillaDSP log
        # started: \(Date())
        # config:  \(configPath.path)
        # ---\n
        """
        if let headerData = header.data(using: .utf8) {
            writeHandle.write(headerData)
        }

        let process = Process()
        process.executableURL = exe
        process.arguments = [
            "-l", debug ? "debug" : "info",
            configPath.path
        ]

        // Direct file redirection to eliminate 16KB pipe buffer deadlocks completely
        process.standardOutput = writeHandle
        process.standardError = writeHandle

        try process.run()
        self.currentProcess = process
        self.activeConfigPath = configPath

        startLogTail(logUrl: logFile)
    }

    public func stop() {
        tailTask?.cancel()
        tailTask = nil

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

    private func startLogTail(logUrl: URL) {
        tailTask?.cancel()
        tailTask = Task.detached { [weak self] in
            guard let readHandle = try? FileHandle(forReadingFrom: logUrl) else { return }
            defer { try? readHandle.close() }

            var offset: UInt64 = 0
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 200_000_000) // 200ms
                guard let curLen = try? readHandle.seekToEnd(), curLen > offset else { continue }
                try? readHandle.seek(toOffset: offset)
                let data = readHandle.readDataToEndOfFile()
                offset += UInt64(data.count)

                if let text = String(data: data, encoding: .utf8), !text.isEmpty {
                    DispatchQueue.main.async {
                        self?.onLogMessage?(text)
                    }
                }
            }
        }
    }
}
