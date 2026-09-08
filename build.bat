@echo off
cd /d "%~dp0"
echo ===================================================
echo   GameLauncher - Building Standalone EXE
echo ===================================================
echo.

py -m pip install -r requirements.txt
echo.
echo Running PyInstaller...
py -m PyInstaller --noconsole --onefile --name "GameLauncher" --collect-all customtkinter --collect-all windnd --clean main.py

if %ERRORLEVEL% EQU 0 (
    echo ===================================================
    echo  Build Successful! Output: dist\GameLauncher.exe
    echo ===================================================
) else (
    echo ===================================================
    echo  Build failed with error code %ERRORLEVEL%
    echo ===================================================
)
pause
