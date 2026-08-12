// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "junvis-mac",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(
            name: "junvis-mac",
            path: "Sources/junvis-mac"
        )
    ]
)
