import Foundation

public enum IndexParser {
    public static func parseAutoEqIndex(rawText: String) -> [String: [HeadphoneEntry]] {
        var entries: [String: [HeadphoneEntry]] = [:]

        let pattern = "\\[([^\\]]+?)\\]\\(([^\\)]+?)\\)"
        guard let regex = try? NSRegularExpression(pattern: pattern, options: []) else {
            return entries
        }

        let nsString = rawText as NSString
        let matches = regex.matches(in: rawText, options: [], range: NSRange(location: 0, length: nsString.length))

        for match in matches {
            guard match.numberOfRanges >= 3 else { continue }
            let nameRange = match.range(at: 1)
            let pathRange = match.range(at: 2)

            let displayName = nsString.substring(with: nameRange)
                .precomposedStringWithCanonicalMapping
                .trimmingCharacters(in: .whitespacesAndNewlines)
            var rawPath = nsString.substring(with: pathRange)
                .precomposedStringWithCanonicalMapping
                .trimmingCharacters(in: .whitespacesAndNewlines)

            if rawPath.hasPrefix("./") {
                rawPath = String(rawPath.dropFirst(2))
            }

            let decodedPath = rawPath.removingPercentEncoding ?? rawPath
            let provider = extractProviderLabel(relativePath: decodedPath)
            let (form, rig) = extractFormAndRig(relativePath: decodedPath)

            let entry = HeadphoneEntry(
                name: displayName,
                form: form,
                rig: rig,
                provider: provider,
                relativePath: decodedPath
            )

            let key = displayName.lowercased()
            entries[key, default: []].append(entry)
        }

        return entries
    }

    public static func extractProviderLabel(relativePath: String) -> String {
        let cleaned = relativePath.replacingOccurrences(of: "\\", with: "/").trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let segments = cleaned.split(separator: "/").map(String.init)
        guard let first = segments.first else { return "default" }
        if first == "offline_csvs" { return "offline" }
        return first
    }

    public static func extractFormAndRig(relativePath: String) -> (form: String, rig: String) {
        let cleaned = relativePath.replacingOccurrences(of: "\\", with: "/").trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let segments = cleaned.split(separator: "/").map(String.init)
        if segments.count >= 2 {
            let rig = segments[1]
            var form = rig
            let low = rig.lowercased()
            if low.contains("over-ear") || low.contains("over_ear") {
                form = "over-ear"
            } else if low.contains("earbud") {
                form = "earbud"
            } else if low.contains("in-ear") || low.contains("in_ear") {
                form = "in-ear"
            }
            return (form, rig)
        }
        return ("headphone", "")
    }
}
