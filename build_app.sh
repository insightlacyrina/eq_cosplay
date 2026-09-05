#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> Building EQCosplay products in Release mode..."
swift build -c release --product EQCosplayApp
swift build -c release --product eq-cosplay-cli

BIN_DIR="$(swift build -c release --show-bin-path)"

APP_NAME="EQ Cosplay.app"
DIST_DIR="$SCRIPT_DIR/dist"
APP_BUNDLE="$DIST_DIR/$APP_NAME"
CONTENTS="$APP_BUNDLE/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"

echo "==> Packaging $APP_NAME..."
mkdir -p "$DIST_DIR"
rm -rf "$APP_BUNDLE"
mkdir -p "$MACOS" "$RESOURCES"

# Copy main binary
cp "$BIN_DIR/EQCosplayApp" "$MACOS/EQCosplayApp"
chmod +x "$MACOS/EQCosplayApp"

# Copy CLI binary to dist for quick terminal use
cp "$BIN_DIR/eq-cosplay-cli" "$DIST_DIR/eq-cosplay-cli"
chmod +x "$DIST_DIR/eq-cosplay-cli"

# Copy bundled CamillaDSP if present
if [ -f "$SCRIPT_DIR/camilladsp" ]; then
    cp "$SCRIPT_DIR/camilladsp" "$RESOURCES/camilladsp"
    chmod +x "$RESOURCES/camilladsp"
elif [ -f "/Users/zhuyongfei/Desktop/eq_cosplay/camilladsp" ]; then
    cp "/Users/zhuyongfei/Desktop/eq_cosplay/camilladsp" "$RESOURCES/camilladsp"
    chmod +x "$RESOURCES/camilladsp"
fi

# Copy assets & fonts
if [ -d "$SCRIPT_DIR/assets" ]; then
    cp -R "$SCRIPT_DIR/assets" "$RESOURCES/"
fi

# Generate AppIcon.icns from assets/icons/app.png
ICON_SRC="$SCRIPT_DIR/assets/icons/app.png"
if [ -f "$ICON_SRC" ]; then
    ICONSET_DIR="$(mktemp -d)/AppIcon.iconset"
    mkdir -p "$ICONSET_DIR"
    sips -z 16 16     "$ICON_SRC" --out "$ICONSET_DIR/icon_16x16.png" >/dev/null 2>&1 || true
    sips -z 32 32     "$ICON_SRC" --out "$ICONSET_DIR/icon_16x16@2x.png" >/dev/null 2>&1 || true
    sips -z 32 32     "$ICON_SRC" --out "$ICONSET_DIR/icon_32x32.png" >/dev/null 2>&1 || true
    sips -z 64 64     "$ICON_SRC" --out "$ICONSET_DIR/icon_32x32@2x.png" >/dev/null 2>&1 || true
    sips -z 128 128   "$ICON_SRC" --out "$ICONSET_DIR/icon_128x128.png" >/dev/null 2>&1 || true
    sips -z 256 256   "$ICON_SRC" --out "$ICONSET_DIR/icon_128x128@2x.png" >/dev/null 2>&1 || true
    sips -z 256 256   "$ICON_SRC" --out "$ICONSET_DIR/icon_256x256.png" >/dev/null 2>&1 || true
    sips -z 512 512   "$ICON_SRC" --out "$ICONSET_DIR/icon_256x256@2x.png" >/dev/null 2>&1 || true
    sips -z 512 512   "$ICON_SRC" --out "$ICONSET_DIR/icon_512x512.png" >/dev/null 2>&1 || true
    sips -z 1024 1024 "$ICON_SRC" --out "$ICONSET_DIR/icon_512x512@2x.png" >/dev/null 2>&1 || true

    iconutil -c icns "$ICONSET_DIR" -o "$RESOURCES/AppIcon.icns" >/dev/null 2>&1 || true
    rm -rf "$(dirname "$ICONSET_DIR")"
fi

# Write Info.plist
cat << 'PLIST' > "$CONTENTS/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>EQCosplayApp</string>
    <key>CFBundleIdentifier</key>
    <string>com.insightlacyrina.eqcosplay</string>
    <key>CFBundleName</key>
    <string>EQ Cosplay</string>
    <key>CFBundleDisplayName</key>
    <string>EQ Cosplay</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.1.6</string>
    <key>CFBundleVersion</key>
    <string>1.1.6</string>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSSupportsAutomaticGraphicsSwitching</key>
    <true/>
    <key>NSMicrophoneUsageDescription</key>
    <string>EQ Cosplay 需要音频捕获权限以接收 BlackHole 虚拟音频流并进行实时均衡校正输出。</string>
</dict>
</plist>
PLIST

# Write Entitlements
cat << 'ENT' > "$CONTENTS/Entitlements.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.device.audio-input</key>
    <true/>
    <key>com.apple.security.get-task-allow</key>
    <true/>
</dict>
</plist>
ENT

# Ad-hoc code sign with audio input entitlements
echo "==> Code signing with audio-input entitlements..."
codesign --force --deep --entitlements "$CONTENTS/Entitlements.plist" -s - "$APP_BUNDLE"
xattr -dr com.apple.quarantine "$APP_BUNDLE" 2>/dev/null || true

echo ""
echo "======================================================="
echo " Build successful!"
echo " Native macOS App: $APP_BUNDLE"
echo " CLI executable:   $DIST_DIR/eq-cosplay-cli"
echo "======================================================="
