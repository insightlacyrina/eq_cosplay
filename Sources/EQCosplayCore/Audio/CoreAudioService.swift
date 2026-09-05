import Foundation
import CoreAudio

public enum CoreAudioService {
    public static let virtualDeviceKeywords = [
        "blackhole",
        "background music",
        "loopback",
        "virtual",
        "multi-output",
        "多输出设备"
    ]

    public static func isVirtualDevice(name: String) -> Bool {
        let low = name.lowercased()
        return virtualDeviceKeywords.contains { low.contains($0) }
    }

    /// Returns ONLY physical playback devices (headphones, speakers, USB DACs),
    /// strictly excluding virtual devices like BlackHole or Background Music.
    public static func getAudioOutputDevices() -> [AudioDevice] {
        let all = getAllAudioDevices()
        let defaultOutputID = getDefaultOutputDeviceID()

        var physicalDevices: [AudioDevice] = []
        for dev in all {
            if !isVirtualDevice(name: dev.name) {
                let isDefault = (dev.id == defaultOutputID)
                physicalDevices.append(AudioDevice(id: dev.id, name: dev.name, uid: dev.uid, isDefault: isDefault))
            }
        }
        return physicalDevices
    }

    /// Returns all output devices, including virtual ones.
    public static func getAllAudioDevices() -> [AudioDevice] {
        var propertyAddress = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDevices,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )

        var dataSize: UInt32 = 0
        var status = AudioObjectGetPropertyDataSize(
            AudioObjectID(kAudioObjectSystemObject),
            &propertyAddress,
            0,
            nil,
            &dataSize
        )

        guard status == noErr, dataSize > 0 else { return [] }

        let deviceCount = Int(dataSize) / MemoryLayout<AudioObjectID>.size
        var deviceIDs = [AudioObjectID](repeating: 0, count: deviceCount)

        status = AudioObjectGetPropertyData(
            AudioObjectID(kAudioObjectSystemObject),
            &propertyAddress,
            0,
            nil,
            &dataSize,
            &deviceIDs
        )

        guard status == noErr else { return [] }

        let defaultOutputID = getDefaultOutputDeviceID()
        var devices: [AudioDevice] = []

        for id in deviceIDs {
            if hasOutputStreams(deviceID: id) {
                let name = getDeviceName(deviceID: id)
                let uid = getDeviceUID(deviceID: id)
                let isDefault = (id == defaultOutputID)
                devices.append(AudioDevice(id: id, name: name, uid: uid, isDefault: isDefault))
            }
        }

        return devices
    }

    public static func getDefaultOutputDeviceID() -> AudioObjectID {
        var propertyAddress = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultOutputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )

        var deviceID: AudioObjectID = 0
        var dataSize = UInt32(MemoryLayout<AudioObjectID>.size)

        let status = AudioObjectGetPropertyData(
            AudioObjectID(kAudioObjectSystemObject),
            &propertyAddress,
            0,
            nil,
            &dataSize,
            &deviceID
        )

        return (status == noErr) ? deviceID : 0
    }

    @discardableResult
    public static func setDefaultOutputDeviceID(_ id: AudioObjectID) -> Bool {
        var propertyAddress = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultOutputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )

        var deviceID = id
        let dataSize = UInt32(MemoryLayout<AudioObjectID>.size)

        let status = AudioObjectSetPropertyData(
            AudioObjectID(kAudioObjectSystemObject),
            &propertyAddress,
            0,
            nil,
            dataSize,
            &deviceID
        )

        return status == noErr
    }

    public static func getDeviceID(named target: String) -> AudioObjectID? {
        let all = getAllAudioDevices()
        let lowTarget = target.lowercased()
        if let exact = all.first(where: { $0.name.lowercased() == lowTarget }) {
            return exact.id
        }
        return all.first(where: { $0.name.lowercased().contains(lowTarget) })?.id
    }

    private static func hasOutputStreams(deviceID: AudioObjectID) -> Bool {
        var propertyAddress = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyStreams,
            mScope: kAudioObjectPropertyScopeOutput,
            mElement: kAudioObjectPropertyElementMain
        )

        var dataSize: UInt32 = 0
        let status = AudioObjectGetPropertyDataSize(
            deviceID,
            &propertyAddress,
            0,
            nil,
            &dataSize
        )

        return (status == noErr && dataSize > 0)
    }

    public static func getDeviceName(deviceID: AudioObjectID) -> String {
        var propertyAddress = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyDeviceNameCFString,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )

        var cfName: Unmanaged<CFString>?
        var dataSize = UInt32(MemoryLayout<CFString?>.size)

        let status = AudioObjectGetPropertyData(
            deviceID,
            &propertyAddress,
            0,
            nil,
            &dataSize,
            &cfName
        )

        if status == noErr, let cf = cfName {
            return cf.takeRetainedValue() as String
        }
        return "Audio Device \(deviceID)"
    }

    public static func getDeviceUID(deviceID: AudioObjectID) -> String {
        var propertyAddress = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyDeviceUID,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )

        var cfUID: Unmanaged<CFString>?
        var dataSize = UInt32(MemoryLayout<CFString?>.size)

        let status = AudioObjectGetPropertyData(
            deviceID,
            &propertyAddress,
            0,
            nil,
            &dataSize,
            &cfUID
        )

        if status == noErr, let cf = cfUID {
            return cf.takeRetainedValue() as String
        }
        return "\(deviceID)"
    }
}
