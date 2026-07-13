@echo off
setlocal EnableExtensions EnableDelayedExpansion
rem EQ Cosplay Windows launcher (GUI by default; pass --cli for terminal)
cd /d "%~dp0"

set "USE_CLI=0"
for %%A in (%*) do (
  if /I "%%~A"=="--cli" set "USE_CLI=1"
  if /I "%%~A"=="-c" set "USE_CLI=1"
)

echo [EQ Cosplay] Starting...
echo [EQ Cosplay] Project: %CD%

rem --- Resolve Python (Windows often has "py" or "python", not "python3") ---
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  where python3 >nul 2>&1 && set "PY=python3"
)
if not defined PY (
  echo [ERR] Python not found. Install Python 3.10+ from https://www.python.org/downloads/
  echo       During setup, enable: "Add python.exe to PATH" and "tcl/tk and IDLE".
  goto :fail
)

echo [OK] Using: %PY%
%PY% -c "import sys; print('[OK] Python', sys.version.split()[0], sys.executable)"
if errorlevel 1 goto :fail

rem --- venv ---
if not exist ".venv\Scripts\python.exe" (
  echo [EQ Cosplay] Creating virtual environment...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo [ERR] Failed to create .venv
    goto :fail
  )
  echo [OK] Virtual environment ready.
)

set "VENV_PY=%CD%\.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo [ERR] .venv\Scripts\python.exe missing
  goto :fail
)

echo [..] Installing dependencies...
"%VENV_PY%" -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  "%VENV_PY%" -m pip install -q --disable-pip-version-check numpy scipy
  if errorlevel 1 (
    echo [ERR] Failed to install numpy/scipy. Check network / proxy.
    goto :fail
  )
)

rem --- GUI requires Tk ---
if "%USE_CLI%"=="0" (
  "%VENV_PY%" -c "import tkinter" 2>nul
  if errorlevel 1 (
    echo [ERR] Tkinter is not available in this Python.
    echo       Fix: reinstall Python from python.org and check "tcl/tk and IDLE".
    echo       Falling back to terminal UI...
    set "USE_CLI=1"
  )
)

if "%USE_CLI%"=="1" (
  echo [OK] Launching terminal UI...
  "%VENV_PY%" cosplay.py
  set "EC=!errorlevel!"
) else (
  echo [OK] Launching GUI...
  rem Use console python.exe (not detached pythonw) so import/Tk errors stay visible.
  rem cosplay_gui.py also shows a MessageBox on fatal startup errors.
  "%VENV_PY%" cosplay_gui.py
  set "EC=!errorlevel!"
)

if not "!EC!"=="0" (
  echo [ERR] Process exited with code !EC!
  goto :fail
)
echo [EQ Cosplay] Done.
exit /b 0

:fail
echo.
echo [EQ Cosplay] Launch failed. See messages above.
pause
exit /b 1
