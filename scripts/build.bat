@echo off
REM Build script for LaunchForge / Yi Jian Duo Qi
REM Keep this file ASCII-only: cmd.exe parses .bat with the local code page,
REM and non-ASCII text in control flow breaks the parser on some machines.
setlocal enabledelayedexpansion
cd /d "%~dp0.."

REM Read APP_VERSION from src\launchforge.py (single source of truth)
for /f "tokens=2 delims='" %%v in ('findstr /b "APP_VERSION" src\launchforge.py') do set APPVER=%%v
if "%APPVER%"=="" (
    echo [ERROR] cannot parse APP_VERSION from src\launchforge.py
    exit /b 1
)
set OUTNAME=LaunchForge_v%APPVER%
echo Version %APPVER%  -^>  %OUTNAME%.exe
echo.

echo [1/3] Install dependencies (mirror)...
python -m pip install -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt pyinstaller
if errorlevel 1 goto :err

echo [2/3] Clean old output...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "%OUTNAME%.spec" del /q "%OUTNAME%.spec"

echo [3/3] Build with PyInstaller...
REM  --onefile        single exe (self-extract to %TEMP% at runtime)
REM  --windowed       GUI, no console window
REM  --add-data       bundle the icon for sys._MEIPASS (separator is ';' on Windows)
REM  --icon           exe file icon
REM  --version-file   VERSIONINFO shown in file properties
python -m PyInstaller --noconfirm --onefile --windowed ^
    --icon=assets\logo.ico ^
    --add-data "assets\logo.ico;." ^
    --version-file=version.txt ^
    --name "%OUTNAME%" ^
    src\launchforge.py
if errorlevel 1 goto :err

copy /y "dist\%OUTNAME%.exe" ".\%OUTNAME%.exe" >nul

echo.
echo [post] Refresh desktop shortcut...
REM A .lnk stores an absolute path, so it MUST be rebuilt after a version bump.
python scripts\update_shortcut.py "%CD%\%OUTNAME%.exe"
if errorlevel 1 echo [WARN] shortcut update failed, point it manually to %OUTNAME%.exe

echo [post] Remove older local builds...
for %%f in ("LaunchForge_v*.exe") do (
    if /i not "%%~nxf"=="%OUTNAME%.exe" del /q "%%f" 2>nul
)

echo.
echo Done: dist\%OUTNAME%.exe
echo Copied to repo root: %OUTNAME%.exe
pause
exit /b 0

:err
echo.
echo Build failed, see the output above.
pause
exit /b 1
