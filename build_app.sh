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

# Copy or auto-acquire CamillaDSP binary
if [ -f "$SCRIPT_DIR/camilladsp" ]; then
    echo "==> Using local $SCRIPT_DIR/camilladsp"
    cp "$SCRIPT_DIR/camilladsp" "$RESOURCES/camilladsp"
    chmod +x "$RESOURCES/camilladsp"
elif [ -f "$HOME/Library/Application Support/EQ Cosplay/bin/camilladsp" ]; then
    echo "==> Using existing Application Support camilladsp"
    cp "$HOME/Library/Application Support/EQ Cosplay/bin/camilladsp" "$RESOURCES/camilladsp"
    chmod +x "$RESOURCES/camilladsp"
elif [ -f "/opt/homebrew/bin/camilladsp" ]; then
    echo "==> Using Homebrew camilladsp"
    cp "/opt/homebrew/bin/camilladsp" "$RESOURCES/camilladsp"
    chmod +x "$RESOURCES/camilladsp"
elif [ -f "/usr/local/bin/camilladsp" ]; then
    echo "==> Using /usr/local/bin/camilladsp"
    cp "/usr/local/bin/camilladsp" "$RESOURCES/camilladsp"
    chmod +x "$RESOURCES/camilladsp"
else
    echo "==> CamillaDSP binary not found locally. Auto-fetching from GitHub Releases..."
    ARCH="$(uname -m)"
    if [ "$ARCH" = "arm64" ]; then
        CAMILLA_TAR="camilladsp-macos-aarch64.tar.gz"
    else
        CAMILLA_TAR="camilladsp-macos-x86_64.tar.gz"
    fi
    CAMILLA_URL="https://github.com/HEnquist/camilladsp/releases/latest/download/$CAMILLA_TAR"
    TMP_TAR_DIR="$(mktemp -d)"
    if curl -sSL -f "$CAMILLA_URL" -o "$TMP_TAR_DIR/$CAMILLA_TAR"; then
        tar -xzf "$TMP_TAR_DIR/$CAMILLA_TAR" -C "$TMP_TAR_DIR"
        cp "$TMP_TAR_DIR/camilladsp" "$SCRIPT_DIR/camilladsp"
        cp "$TMP_TAR_DIR/camilladsp" "$RESOURCES/camilladsp"
        chmod +x "$SCRIPT_DIR/camilladsp" "$RESOURCES/camilladsp"
        rm -rf "$TMP_TAR_DIR"
        echo "==> CamillaDSP acquired and bundled successfully."
    else
        echo "==> Warning: Failed to auto-download CamillaDSP during build. App will attempt on-demand download."
        rm -rf "$TMP_TAR_DIR"
    fi
fi

# Copy assets & fonts
if [ -d "$SCRIPT_DIR/assets" ]; then
    cp -R "$SCRIPT_DIR/assets" "$RESOURCES/"
fi

# Copy presets
if [ -d "$SCRIPT_DIR/presets" ]; then
    cp -R "$SCRIPT_DIR/presets" "$RESOURCES/"
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
    <string>1.1.7</string>
    <key>CFBundleVersion</key>
    <string>1.1.7</string>
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

# Prepare DMG staging
echo "==> Packaging DMG & ZIP distribution artifacts for v1.1.7..."
DMG_STAGE="$DIST_DIR/dmg"
mkdir -p "$DMG_STAGE"
rm -rf "$DMG_STAGE/$APP_NAME"
cp -R "$APP_BUNDLE" "$DMG_STAGE/"
if [ ! -L "$DMG_STAGE/Applications" ]; then
    ln -s /Applications "$DMG_STAGE/Applications"
fi

# Create DMG
DMG_OUT="$DIST_DIR/EQ-Cosplay-v1.1.7-macOS.dmg"
rm -f "$DMG_OUT"
hdiutil create -volname "EQ Cosplay" -srcfolder "$DMG_STAGE" -ov -format UDZO "$DMG_OUT" >/dev/null

# Create ZIP
(cd "$DIST_DIR" && rm -f "EQ-Cosplay-v1.1.7-macOS.zip" && zip -q -r -y "EQ-Cosplay-v1.1.7-macOS.zip" "$APP_NAME")

# Create CLI Tarball
(cd "$DIST_DIR" && rm -f "eq-cosplay-cli-v1.1.7-macOS-arm64.tar.gz" && tar -czf "eq-cosplay-cli-v1.1.7-macOS-arm64.tar.gz" "eq-cosplay-cli")

echo ""
echo "======================================================="
echo " Build & packaging successful!"
echo " Native macOS App: $APP_BUNDLE"
echo " DMG artifact:     $DMG_OUT"
echo " ZIP artifact:     $DIST_DIR/EQ-Cosplay-v1.1.7-macOS.zip"
echo " CLI artifact:     $DIST_DIR/eq-cosplay-cli-v1.1.7-macOS-arm64.tar.gz"
echo "======================================================="
