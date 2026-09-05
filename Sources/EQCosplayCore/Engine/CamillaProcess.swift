import Foundation

public final class CamillaProcess: @unchecked Sendable {
    public static let shared = CamillaProcess()

    private var currentProcess: Process?
    private var logFileHandle: FileHandle?
    private var tailTask: Task<Void, Never>?
    public private(set) var activeConfigPath: URL?
    public var onLogMessage: ((String) -> Void)?
    public var onProcessTerminated: ((Int32) -> Void)?

    public var isRunning: Bool {
        guard let p = currentProcess else { return false }
        return p.isRunning
    }

    private init() {}

    public static func getLogsDirectory() -> URL {
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let dir = appSupport.appendingPathComponent("EQ Cosplay/logs", isDirectory: true)
        do {
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            let testFile = dir.appendingPathComponent(".wtest_\(UUID().uuidString)")
            try "ok".write(to: testFile, atomically: true, encoding: .utf8)
            try? FileManager.default.removeItem(at: testFile)
            return dir
        } catch {
            let cwdLogs = URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent("logs", isDirectory: true)
            if (try? FileManager.default.createDirectory(at: cwdLogs, withIntermediateDirectories: true)) != nil {
                return cwdLogs
            }
            let tmpDir = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("EQCosplay/logs", isDirectory: true)
            try? FileManager.default.createDirectory(at: tmpDir, withIntermediateDirectories: true)
            return tmpDir
        }
    }

    public static func getBinDirectory() -> URL {
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let dir = appSupport.appendingPathComponent("EQ Cosplay/bin", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    public static func findExecutable() -> URL? {
        // 1. Check App bundle Resources
        if let bundleUrl = Bundle.main.url(forResource: "camilladsp", withExtension: nil) {
            return bundleUrl
        }
        if let resourceDir = Bundle.main.resourceURL?.appendingPathComponent("camilladsp"),
           FileManager.default.isExecutableFile(atPath: resourceDir.path) {
            return resourceDir
        }

        // 2. Candidate paths
        let home = FileManager.default.homeDirectoryForCurrentUser
        let cwd = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        let candidates = [
            getBinDirectory().appendingPathComponent("camilladsp"),
            cwd.appendingPathComponent("camilladsp"),
            cwd.appendingPathComponent("dist/EQ Cosplay.app/Contents/Resources/camilladsp"),
            Bundle.main.bundleURL.deletingLastPathComponent().appendingPathComponent("camilladsp"),
            URL(fileURLWithPath: "/opt/homebrew/bin/camilladsp"),
            URL(fileURLWithPath: "/usr/local/bin/camilladsp"),
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

    @discardableResult
    public static func downloadCamillaDSP(onLog: ((String) -> Void)? = nil) async throws -> URL {
        let binDir = getBinDirectory()
        let destExe = binDir.appendingPathComponent("camilladsp")
        if FileManager.default.isExecutableFile(atPath: destExe.path) {
            return destExe
        }

        #if arch(arm64)
        let archTar = "camilladsp-macos-aarch64.tar.gz"
        #else
        let archTar = "camilladsp-macos-x86_64.tar.gz"
        #endif

        onLog?("[..] 正在自动从 GitHub Releases 下载 CamillaDSP (\(archTar))...")

        guard let releaseURL = URL(string: "https://github.com/HEnquist/camilladsp/releases/latest/download/\(archTar)") else {
            throw NSError(domain: "CamillaProcess", code: 400, userInfo: [NSLocalizedDescriptionKey: "无效的 CamillaDSP 下载地址"])
        }

        let tempTar = binDir.appendingPathComponent(archTar)
        try? FileManager.default.removeItem(at: tempTar)

        var request = URLRequest(url: releaseURL, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 45)
        request.setValue("EQCosplay/1.1.7 (macOS)", forHTTPHeaderField: "User-Agent")

        let (tempFile, response) = try await URLSession.shared.download(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            let code = (response as? HTTPURLResponse)?.statusCode ?? -1
            throw NSError(domain: "CamillaProcess", code: code, userInfo: [NSLocalizedDescriptionKey: "下载 CamillaDSP 失败 (HTTP \(code))"])
        }

        try FileManager.default.moveItem(at: tempFile, to: tempTar)
        onLog?("[..] 正在解压 CamillaDSP 归档...")

        let tarProc = Process()
        tarProc.executableURL = URL(fileURLWithPath: "/usr/bin/tar")
        tarProc.arguments = ["-xzf", tempTar.path, "-C", binDir.path]
        try tarProc.run()
        tarProc.waitUntilExit()

        try? FileManager.default.removeItem(at: tempTar)

        guard FileManager.default.isExecutableFile(atPath: destExe.path) || FileManager.default.fileExists(atPath: destExe.path) else {
            throw NSError(domain: "CamillaProcess", code: 500, userInfo: [NSLocalizedDescriptionKey: "解压后未找到 camilladsp 可执行程序"])
        }

        // Set executable permissions
        try? FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: destExe.path)

        // Clear quarantine flag
        let xattrProc = Process()
        xattrProc.executableURL = URL(fileURLWithPath: "/usr/bin/xattr")
        xattrProc.arguments = ["-dr", "com.apple.quarantine", destExe.path]
        try? xattrProc.run()
        xattrProc.waitUntilExit()

        onLog?("[OK] CamillaDSP 已安装就绪: \(destExe.path)")
        return destExe
    }

    public static func ensureExecutable(onLog: ((String) -> Void)? = nil) async throws -> URL {
        if let existing = findExecutable() {
            return existing
        }
        return try await downloadCamillaDSP(onLog: onLog)
    }

    public static func stopExistingInstances() {
        let pkillTerm = Process()
        pkillTerm.executableURL = URL(fileURLWithPath: "/usr/bin/pkill")
        pkillTerm.arguments = ["-15", "-x", "camilladsp"]
        try? pkillTerm.run()
        pkillTerm.waitUntilExit()

        Thread.sleep(forTimeInterval: 0.1)

        let pkillKill = Process()
        pkillKill.executableURL = URL(fileURLWithPath: "/usr/bin/pkill")
        pkillKill.arguments = ["-9", "-x", "camilladsp"]
        try? pkillKill.run()
        pkillKill.waitUntilExit()
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

        let logsDir = Self.getLogsDirectory()
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

        process.terminationHandler = { [weak self] proc in
            let code = proc.terminationStatus
            DispatchQueue.main.async {
                self?.onProcessTerminated?(code)
            }
        }

        // Direct file redirection to eliminate 16KB pipe buffer deadlocks completely
        process.standardOutput = writeHandle
        process.standardError = writeHandle

        try process.run()
        self.currentProcess = process
        self.activeConfigPath = configPath

        startLogTail(logUrl: logFile)

        // Health check: verify process did not crash/exit immediately
        Thread.sleep(forTimeInterval: 0.35)
        if !process.isRunning {
            let exitCode = process.terminationStatus
            let logSnippet = (try? String(contentsOf: logFile, encoding: .utf8)) ?? ""
            let lastLines = logSnippet.components(separatedBy: .newlines).suffix(12).joined(separator: "\n")
            self.stop()
            throw NSError(
                domain: "CamillaProcess",
                code: Int(exitCode),
                userInfo: [NSLocalizedDescriptionKey: "CamillaDSP 启动后立即退出 (退出码: \(exitCode))。\n\(lastLines)"]
            )
        }
    }

    public func stop() {
        tailTask?.cancel()
        tailTask = nil

        if let p = currentProcess, p.isRunning {
            p.terminationHandler = nil
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
