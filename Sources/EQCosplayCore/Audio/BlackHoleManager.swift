import Foundation
import CoreAudio

public enum BlackHoleManager {
    public static func isBlackHoleInstalled() -> Bool {
        let devices = CoreAudioService.getAllAudioDevices()
        return devices.contains { $0.name.lowercased().contains("blackhole") }
    }

    public static func getBlackHoleDevice() -> AudioDevice? {
        let devices = CoreAudioService.getAllAudioDevices()
        return devices.first { $0.name.lowercased().contains("blackhole 2ch") }
            ?? devices.first { $0.name.lowercased().contains("blackhole") }
    }

    public static func getBlackHoleDeviceID() -> AudioObjectID? {
        getBlackHoleDevice()?.id
    }

    public static let installInstructions = """
    BlackHole 2ch 虚拟音频设备安装指引：
    1. 使用 Homebrew 安装：
       brew install --cask blackhole-2ch
    2. 或前往官网下载安装包：
       https://existential.audio/blackhole/
    安装完成后，将 macOS 系统声音输出设置为 BlackHole 2ch，CamillaDSP 即可捕获全局音频。
    """

    public static func findBrewExecutable() -> URL? {
        let candidates = [
            URL(fileURLWithPath: "/opt/homebrew/bin/brew"),
            URL(fileURLWithPath: "/usr/local/bin/brew")
        ]
        for c in candidates {
            if FileManager.default.isExecutableFile(atPath: c.path) {
                return c
            }
        }
        let whichProcess = Process()
        whichProcess.executableURL = URL(fileURLWithPath: "/usr/bin/which")
        whichProcess.arguments = ["brew"]
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

    public static func openBlackHoleDownloadPage() {
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        proc.arguments = ["https://existential.audio/blackhole/"]
        try? proc.run()
    }

    @discardableResult
    public static func installBlackHole(onLog: @escaping (String) -> Void) async -> Bool {
        if isBlackHoleInstalled() {
            onLog("[OK] BlackHole 虚拟声卡驱动已就绪。")
            return true
        }

        if let brew = findBrewExecutable() {
            onLog("[..] 检测到 Homebrew (\(brew.path))，正在安装 BlackHole 2ch...")
            let proc = Process()
            proc.executableURL = brew
            proc.arguments = ["install", "--cask", "blackhole-2ch"]
            let pipe = Pipe()
            proc.standardOutput = pipe
            proc.standardError = pipe

            do {
                try proc.run()
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                proc.waitUntilExit()

                if let output = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines),
                   !output.isEmpty {
                    for line in output.components(separatedBy: .newlines) {
                        onLog("[brew] \(line)")
                    }
                }

                if proc.terminationStatus == 0 {
                    onLog("[..] 等待 CoreAudio 载入新音频驱动...")
                    try? await Task.sleep(nanoseconds: 2_000_000_000)
                    if isBlackHoleInstalled() {
                        onLog("[OK] BlackHole 2ch 驱动安装并加载成功！")
                        return true
                    }
                } else {
                    onLog("[WARN] Homebrew 安装未完成 (状态码: \(proc.terminationStatus))。")
                }
            } catch {
                onLog("[ERR] 启动 brew 进程失败: \(error.localizedDescription)")
            }
        } else {
            onLog("[i] 未检测到 Homebrew 环境。")
        }

        onLog("[..] 正在打开 BlackHole 官方下载安装页面...")
        openBlackHoleDownloadPage()
        return false
    }
}
