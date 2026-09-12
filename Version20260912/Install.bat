@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo   Thai Stock Dashboard - Setup
echo ==========================================
echo.

if not exist venv (
    echo Creating a private Python environment for this app...
    python -m venv venv
    if errorlevel 1 (
        echo.
        echo ERROR: Python was not found on this computer.
        echo Please install it from https://www.python.org/downloads/
        echo During install, make sure to check "Add Python to PATH".
        echo Then run this file again.
        echo.
        pause
        exit /b 1
    )
) else (
    echo Python environment already exists - skipping creation.
)

echo.
echo Installing required packages... this can take a few minutes,
echo especially the first time.
call venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: Package installation failed. Check the messages above.
    pause
    exit /b 1
)

REM Skip Streamlit's one-time "enter your email" prompt so the app never
REM waits on input it can't show when launched silently.
if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit"
> "%USERPROFILE%\.streamlit\credentials.toml" echo [general]
>> "%USERPROFILE%\.streamlit\credentials.toml" echo email = ""

echo.
echo Creating a Desktop shortcut...
powershell -NoProfile -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut('%USERPROFILE%\Desktop\Thai Stock Dashboard.lnk'); $s.TargetPath='%~dp0Run Dashboard.vbs'; $s.WorkingDirectory='%~dp0'; $s.Description='Thai Stock (SET) Dashboard'; $s.Save()"

echo.
echo ==========================================
echo   Setup complete!
echo.
echo   A shortcut called "Thai Stock Dashboard" was
echo   added to your Desktop. Double-click it any time
echo   to start the app - no need to open this window again.
echo ==========================================
echo.
pause
