// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "EQCosplay",
    defaultLocalization: "en",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .library(name: "EQCosplayCore", targets: ["EQCosplayCore"]),
        .executable(name: "EQCosplayApp", targets: ["EQCosplayApp"]),
        .executable(name: "eq-cosplay-cli", targets: ["EQCosplayCLI"]),
        .executable(name: "eq-cosplay-tests", targets: ["EQCosplayTests"])
    ],
    dependencies: [],
    targets: [
        .target(
            name: "EQCosplayCore",
            dependencies: [],
            path: "Sources/EQCosplayCore"
        ),
        .executableTarget(
            name: "EQCosplayApp",
            dependencies: ["EQCosplayCore"],
            path: "Sources/EQCosplayApp"
        ),
        .executableTarget(
            name: "EQCosplayCLI",
            dependencies: ["EQCosplayCore"],
            path: "Sources/EQCosplayCLI"
        ),
        .executableTarget(
            name: "EQCosplayTests",
            dependencies: ["EQCosplayCore"],
            path: "Tests/EQCosplayTests"
        )
    ]
)
