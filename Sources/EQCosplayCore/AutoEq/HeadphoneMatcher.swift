import Foundation

public enum HeadphoneMatcher {
    public static func search(
        query: String,
        in database: [String: [HeadphoneEntry]],
        limit: Int = 25
    ) -> [HeadphoneEntry] {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return [] }

        let qLower = trimmed.lowercased()
        let qCompact = qLower.replacingOccurrences(of: " ", with: "")
            .replacingOccurrences(of: "-", with: "")
            .replacingOccurrences(of: "_", with: "")
        let qTokens = qLower.split(separator: " ").map(String.init)

        var scored: [(entry: HeadphoneEntry, score: Int)] = []

        for (_, list) in database {
            for entry in list {
                let name = entry.name
                let nameLower = name.lowercased()
                let nameCompact = nameLower.replacingOccurrences(of: " ", with: "")
                    .replacingOccurrences(of: "-", with: "")
                    .replacingOccurrences(of: "_", with: "")

                var score = 0

                if name == trimmed {
                    score = 10000
                } else if nameLower == qLower {
                    score = 9000
                } else if nameCompact == qCompact {
                    score = 8000
                } else if nameLower.hasPrefix(qLower) {
                    score = 6000 - min(name.count - query.count, 200)
                } else if nameCompact.hasPrefix(qCompact) {
                    score = 5000 - min(nameCompact.count - qCompact.count, 200)
                } else if nameLower.contains(qLower) {
                    score = 4000 - min(name.count - query.count, 200)
                } else if nameCompact.contains(qCompact) {
                    score = 3000 - min(nameCompact.count - qCompact.count, 200)
                } else {
                    // Check token coverage
                    var allTokensFound = true
                    for t in qTokens {
                        if !nameLower.contains(t) && !nameCompact.contains(t) {
                            allTokensFound = false
                            break
                        }
                    }
                    if allTokensFound && !qTokens.isEmpty {
                        score = 2500 - min(name.count - query.count, 300)
                    }
                }

                // Provider priority boost (e.g. oratory1990 > crinacle > rtings)
                if score > 0 {
                    let pLower = entry.provider.lowercased()
                    if pLower.contains("oratory") {
                        score += 15
                    } else if pLower.contains("crinacle") {
                        score += 10
                    } else if pLower.contains("rtings") {
                        score += 5
                    }
                    scored.append((entry, score))
                }
            }
        }

        scored.sort { $0.score > $1.score }

        var results: [HeadphoneEntry] = []
        var seenIds = Set<String>()

        for item in scored {
            if results.count >= limit { break }
            if !seenIds.contains(item.entry.id) {
                seenIds.insert(item.entry.id)
                results.append(item.entry)
            }
        }

        return results
    }
}
