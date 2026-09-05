import Foundation

public enum BlackHoleManager {
    public static func isBlackHoleInstalled() -> Bool {
        let devices = CoreAudioService.getAudioOutputDevices()
        return devices.contains { $0.name.lowercased().contains("blackhole") }
    }

    public static func getBlackHoleDevice() -> AudioDevice? {
        let devices = CoreAudioService.getAudioOutputDevices()
        return devices.first { $0.name.lowercased().contains("blackhole 2ch") }
            ?? devices.first { $0.name.lowercased().contains("blackhole") }
    }

    public static let installInstructions = """
    BlackHole 2ch 虚拟音频设备安装指引：
    1. 使用 Homebrew 安装：
       brew install blackhole-2ch
    2. 或前往官网下载安装包：
       https://existential.audio/blackhole/
    安装完成后，将 macOS 系统声音输出设置为 BlackHole 2ch，CamillaDSP 即可捕获全局音频。
    """
}
