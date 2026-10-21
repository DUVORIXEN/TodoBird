@echo off
echo ==============================================
echo Building TODO BIRD for Windows 10 ^& 11
echo ==============================================

cd /d "%~dp0.."

echo 1. Installing build dependencies...
python -m pip install --upgrade pip
python -m pip install pyinstaller PySide6 pyttsx3

echo 2. Compiling standalone executable with PyInstaller...
python -m PyInstaller --clean --noconfirm windows\TodoBird.spec

echo 3. Compiling Windows Setup Installer with Inno Setup (if installed)...
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
    "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" windows\installer.iss
    echo Setup installer built in windows\dist\
) else if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" (
    "%ProgramFiles%\Inno Setup 6\ISCC.exe" windows\installer.iss
    echo Setup installer built in windows\dist\
) else (
    echo [NOTE] Inno Setup 6 not found.
    echo Standalone executable is ready in dist\TodoBird\TodoBird.exe
)

echo ==============================================
echo Build Complete!
echo ==============================================
pause
