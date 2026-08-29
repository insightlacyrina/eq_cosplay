# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: macOS .app (onedir) and Windows .exe (onefile)."""

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

sys.setrecursionlimit(sys.getrecursionlimit() * 5)

ROOT = Path(SPECPATH).resolve()
ONEFILE = sys.platform == "win32"
ICON_ICNS = ROOT / "packaging" / "EQCosplay.icns"
ICON_ICO = ROOT / "packaging" / "EQCosplay.ico"
if sys.platform == "win32":
    ICON = str(ICON_ICO) if ICON_ICO.is_file() else None
else:
    ICON = str(ICON_ICNS) if ICON_ICNS.is_file() else None

datas = []
binaries = []
hiddenimports = [
    "numpy",
    "scipy",
    "scipy.optimize",
    "scipy.io",
    "scipy.io.wavfile",
    "scipy.signal",
    "theme",
    "menubar_macos",
    "cosplay",
]

for pkg in ("numpy", "scipy"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

assets = ROOT / "assets"
if assets.is_dir():
    datas.append((str(assets), "assets"))

for name in ("camilladsp", "camilladsp.exe"):
    candidate = ROOT / name
    if candidate.is_file():
        binaries.append((str(candidate), "."))

a = Analysis(
    [str(ROOT / "cosplay_gui.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "tkinter.test"],
    noarchive=False,
)

pyz = PYZ(a.pure)

if ONEFILE:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name="EQCosplay",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        icon=ICON,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="EQCosplay",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=sys.platform == "darwin",
        icon=ICON,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        name="EQCosplay",
    )
    if sys.platform == "darwin":
        app = BUNDLE(
            coll,
            name="EQ Cosplay.app",
            icon=ICON,
            bundle_identifier="com.eqcosplay.app",
            info_plist={
                "CFBundleName": "EQ Cosplay",
                "CFBundleDisplayName": "EQ Cosplay",
                "CFBundleShortVersionString": "1.0.0",
                "CFBundleVersion": "1.0.0",
                "NSHighResolutionCapable": True,
                "LSMinimumSystemVersion": "11.0",
                "LSUIElement": False,
            },
        )
