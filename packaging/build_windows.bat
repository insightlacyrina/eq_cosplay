@echo off
setlocal EnableExtensions EnableDelayedExpansion
rem Build EQCosplay.exe (onefile) on Windows.
cd /d "%~dp0\.."

set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

echo [EQ Cosplay] Building Windows EXE with %PY%
%PY% -m pip install -q --disable-pip-version-check -r requirements.txt
%PY% -m pip install -q --disable-pip-version-check "pyinstaller>=6.0" pillow
%PY% packaging\make_icons.py
if exist build rmdir /s /q build
%PY% -m PyInstaller --noconfirm --clean eq_cosplay.spec

if exist dist\EQCosplay.exe (
  echo [OK] dist\EQCosplay.exe
) else (
  echo [ERR] dist\EQCosplay.exe was not produced
  exit /b 1
)
exit /b 0
