@echo off
TITLE Build AI Smart Home Voice Hub Desktop (.exe)
COLOR 0B
echo ==============================================================================
echo        AI-Powered Smart Home Voice Hub - Native Windows .exe Compiler
echo        Optimized for Lenovo LOQ RTX 4050 6GB + Groq LPU + Egyptian Audio
echo ==============================================================================
echo.

IF EXIST ".venv\Scripts\python.exe" (
    SET "PY_EXE=.venv\Scripts\python.exe"
    SET "PIP_EXE=.venv\Scripts\pip.exe"
    SET "PYINSTALLER_EXE=.venv\Scripts\pyinstaller.exe"
) ELSE (
    SET "PY_EXE=python"
    SET "PIP_EXE=pip"
    SET "PYINSTALLER_EXE=pyinstaller"
)

echo [*] Using Python: %PY_EXE%

echo [*] Checking audio cache and reference voices...
%PY_EXE% scripts\generate_reference_voices.py
%PY_EXE% scripts\pregenerate_voice_bank.py

echo.
echo [*] Compiling Standalone Windows Desktop Application (.exe)...
echo [*] Configuration: app.spec (Windowed - No Console Popup)
echo.

%PYINSTALLER_EXE% --noconfirm app.spec

if exist "dist\SmartHomeVoiceHub" (
    echo [*] Synchronizing assets to dist folder...
    xcopy /E /I /Y "audio_cache" "dist\SmartHomeVoiceHub\audio_cache" >nul
    xcopy /E /I /Y "config" "dist\SmartHomeVoiceHub\config" >nul
)

IF %ERRORLEVEL% EQU 0 (
    echo.
    echo ==============================================================================
    echo [SUCCESS] Windows Desktop Application EXE Compiled Successfully!
    echo.
    echo Compiled Executable Location:
    echo   dist\SmartHomeVoiceHub\SmartHomeVoiceHub.exe
    echo.
    echo Double-click SmartHomeVoiceHub.exe to launch your Native Smart Home Hub!
    echo ==============================================================================
) ELSE (
    echo.
    echo [ERROR] PyInstaller compilation failed.
)

pause
