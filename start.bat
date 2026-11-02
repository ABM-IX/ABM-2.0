@echo off
echo Starting ABM 2.0 Desktop Tray App...
echo.

REM Activate the virtual environment if it exists (assuming it's named .venv or venv)
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

REM Check for required dependencies (voice deps added 2026-11-02)
python -c "import pystray, PIL, dotenv, webview, sounddevice, pyttsx3" 2>NUL
if %errorlevel% neq 0 (
    echo Installing required desktop app dependencies...
    pip install pystray Pillow python-dotenv requests pywebview sounddevice pyttsx3
)

REM Noise suppression for the always-listening wake word (2026-11-02).
REM Optional and fails open — voice input still works without it, so a
REM failed install here is only logged, never blocks startup.
python -c "import numpy, pywebrtc_audio" 2>NUL
if %errorlevel% neq 0 (
    echo Installing optional noise-suppression dependency...
    pip install numpy pywebrtc-audio==0.2.0 2>NUL
)

REM Start the tray app without keeping the command prompt open
start /B pythonw -m abm.tray_app

echo ABM 2.0 is starting — its window will open on its own in a few seconds.
echo (An indigo icon also appears in your system tray if you need it.)
echo This window will close itself.
timeout /t 3 >NUL
