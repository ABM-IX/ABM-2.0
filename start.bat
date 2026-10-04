@echo off
echo Starting ABM 2.0 Desktop Tray App...
echo.

REM Activate the virtual environment if it exists (assuming it's named .venv or venv)
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

REM Check for required dependencies
python -c "import pystray, PIL, dotenv, webview" 2>NUL
if %errorlevel% neq 0 (
    echo Installing required desktop app dependencies...
    pip install pystray Pillow python-dotenv requests pywebview
)

REM Start the tray app without keeping the command prompt open
start /B pythonw -m abm.tray_app

echo ABM 2.0 has been started and is running in your system tray!
echo Look for the indigo circle icon in your bottom right taskbar.
echo You can close this window now.
echo.
pause
