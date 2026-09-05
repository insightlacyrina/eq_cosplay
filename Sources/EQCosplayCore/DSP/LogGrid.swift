import Foundation

public enum LogGrid {
    public static func makeLogFreqs(numPoints: Int = 512, fmin: Double = 20.0, fmax: Double = 20000.0) -> [Double] {
        guard numPoints > 1 else { return [fmin] }
        let logMin = log10(fmin)
        let logMax = log10(fmax)
        let step = (logMax - logMin) / Double(numPoints - 1)
        return (0..<numPoints).map { pow(10.0, logMin + Double($0) * step) }
    }

    public static func interp(x: [Double], xp: [Double], yp: [Double]) -> [Double] {
        guard !xp.isEmpty && !yp.isEmpty && xp.count == yp.count else {
            return [Double](repeating: 0.0, count: x.count)
        }
        guard xp.count > 1 else {
            return [Double](repeating: yp[0], count: x.count)
        }

        var result = [Double](repeating: 0.0, count: x.count)
        var p = 0

        for (i, targetX) in x.enumerated() {
            if targetX <= xp[0] {
                result[i] = yp[0]
                continue
            }
            if targetX >= xp[xp.count - 1] {
                result[i] = yp[yp.count - 1]
                continue
            }

            while p < xp.count - 2 && xp[p + 1] < targetX {
                p += 1
            }

            let x0 = xp[p]
            let x1 = xp[p + 1]
            let y0 = yp[p]
            let y1 = yp[p + 1]
            let t = (targetX - x0) / max(x1 - x0, 1e-12)
            result[i] = y0 + t * (y1 - y0)
        }

        return result
    }
}
