#!/bin/bash
# Build EQ Cosplay.app and wrap it in a UDZO DMG.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-python3}"
if [ -x "$ROOT/.venv/bin/python" ]; then
  PY="$ROOT/.venv/bin/python"
fi

echo "[EQ Cosplay] Building macOS app with $PY"
"$PY" -m pip install -q --disable-pip-version-check -r requirements.txt
"$PY" -m pip install -q --disable-pip-version-check "pyinstaller>=6.0" pillow
if ! "$PY" -c "import Cocoa" 2>/dev/null; then
  "$PY" -m pip install -q --disable-pip-version-check "pyobjc-framework-Cocoa>=10.0" || true
fi

"$PY" packaging/make_icons.py

rm -rf build dist/EQCosplay dist/"EQ Cosplay.app" dist/dmg
"$PY" -m PyInstaller --noconfirm --clean eq_cosplay.spec

APP="dist/EQ Cosplay.app"
if [ ! -d "$APP" ]; then
  echo "[ERR] $APP was not produced"
  exit 1
fi

# Drop quarantine so first-run Gatekeeper is less painful for local builds.
if command -v xattr >/dev/null 2>&1; then
  xattr -cr "$APP" 2>/dev/null || true
fi

STAGE="dist/dmg"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/EQ Cosplay.app"
ln -s /Applications "$STAGE/Applications"

DMG="dist/EQ-Cosplay-macOS.dmg"
rm -f "$DMG"
hdiutil create \
  -volname "EQ Cosplay" \
  -srcfolder "$STAGE" \
  -ov -format UDZO \
  "$DMG"

echo "[OK] $DMG"
ls -lh "$DMG"
