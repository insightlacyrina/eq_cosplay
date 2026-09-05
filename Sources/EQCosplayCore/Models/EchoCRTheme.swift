import SwiftUI

public enum EchoCRTheme {
    // Hex Color Helper
    public static func hexColor(_ hex: UInt32, alpha: Double = 1.0) -> Color {
        let r = Double((hex >> 16) & 0xff) / 255.0
        let g = Double((hex >> 8) & 0xff) / 255.0
        let b = Double(hex & 0xff) / 255.0
        return Color(.sRGB, red: r, green: g, blue: b, opacity: alpha)
    }

    // Core EchoCR Dark Palette
    public static let bg = hexColor(0x0b0d11)
    public static let panel = hexColor(0x12161d)
    public static let border = hexColor(0x2a3340)
    public static let text = hexColor(0xe8edf4)
    public static let muted = hexColor(0x8b97a8)
    public static let gold = hexColor(0xd4a24a)
    public static let teal = hexColor(0x5eead4)
    public static let emerald = hexColor(0x34d399)
    public static let rose = hexColor(0xf87171)
    public static let slot = hexColor(0x1a212c)
    public static let input = hexColor(0x0e1319)
    public static let button = hexColor(0x1c232e)
    public static let primaryBg = hexColor(0x12352f)
    public static let primaryLine = hexColor(0x2d6a62)
    public static let goldBg = hexColor(0x2a210f)
    public static let logBg = hexColor(0x0a0d11)
    public static let logFg = hexColor(0xc5d0dc)

    // Plot Specific
    public static let plotFace = hexColor(0x0e1319)
    public static let plotGrid = hexColor(0x2a3340)
    public static let plotSource = hexColor(0x5eead4)    // Teal
    public static let plotTarget = hexColor(0xd4a24a)    // Gold
    public static let plotSimulated = hexColor(0x34d399) // Emerald
    public static let plotDelta = hexColor(0xf87171)     // Rose

    // Typography
    public static let fontDisplay = "AR FangXinShuH7GBK"
    public static let fontMono = "JetBrains Mono"
}
