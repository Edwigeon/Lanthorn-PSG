@echo off
REM ============================================================
REM Lanthorn PSG v0.3 - Windows Build Script
REM Run this from the lanthorn_psg directory after installing Python.
REM Automatically downloads ffmpeg and builds a Windows installer
REM with NSIS if makensis is available.
REM ============================================================

setlocal EnableDelayedExpansion

echo.
echo  Lanthorn PSG - Windows Build
echo  ================================
echo.

REM ---- Check Python ----
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found. Install Python 3.12+ from python.org
    echo  Make sure "Add Python to PATH" is checked during install.
    pause
    exit /b 1
)

REM ---- Install Python dependencies ----
echo  Installing Python dependencies...
python -m pip install -r requirements.txt
python -m pip install pyinstaller

REM ---- Fetch ffmpeg for Windows (required by pydub for MP3 export) ----
echo.
echo  Checking for bundled ffmpeg...
if not exist "tools\ffmpeg\ffmpeg.exe" (
    echo  Downloading ffmpeg...

    if not exist tools mkdir tools

    REM Try curl.exe first (built into Windows 10/11 - fast)
    REM Fall back to PowerShell with progress bar suppressed (Invoke-WebRequest is very slow without this)
    where curl.exe >nul 2>&1
    if !errorlevel! == 0 (
        echo  Downloading with curl...
        curl.exe -L --progress-bar -o "tools\ffmpeg_dl.zip" "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    ) else (
        echo  Downloading with PowerShell...
        powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip' -OutFile 'tools\ffmpeg_dl.zip' -UseBasicParsing"
    )

    if not exist "tools\ffmpeg_dl.zip" (
        echo  ERROR: Failed to download ffmpeg. Check your internet connection.
        echo  You can manually place ffmpeg.exe and ffprobe.exe in tools\ffmpeg\
        pause
        exit /b 1
    )

    echo  Extracting ffmpeg...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path 'tools\ffmpeg_dl.zip' -DestinationPath 'tools\ffmpeg_tmp' -Force"

    REM The zip contains a single top-level folder; grab the bin\ contents
    for /d %%D in (tools\ffmpeg_tmp\*) do (
        if exist "%%D\bin\ffmpeg.exe" (
            if not exist "tools\ffmpeg" mkdir tools\ffmpeg
            copy /y "%%D\bin\ffmpeg.exe"  "tools\ffmpeg\" >nul
            copy /y "%%D\bin\ffprobe.exe" "tools\ffmpeg\" >nul
        )
    )

    del /q tools\ffmpeg_dl.zip 2>nul
    rmdir /s /q tools\ffmpeg_tmp 2>nul

    if exist "tools\ffmpeg\ffmpeg.exe" (
        echo  ffmpeg downloaded successfully.
    ) else (
        echo  WARNING: Could not extract ffmpeg.exe automatically.
        echo  Please manually place ffmpeg.exe and ffprobe.exe in tools\ffmpeg\
    )
) else (
    echo  ffmpeg already present - skipping download.
)

REM ---- Build with PyInstaller ----
echo.
echo  Building executable...
python -m PyInstaller lanthorn_psg.spec --clean

if not exist "dist\LanthornPSG.exe" (
    echo.
    echo  BUILD FAILED - check errors above.
    pause
    exit /b 1
)

REM ---- Copy supporting files into dist\ ----
echo.
echo  Copying supporting files to dist\...
xcopy /e /i /y presets dist\presets\ >nul
copy /y ENGINE_SPEC.md  dist\ >nul
copy /y LICENSE         dist\ >nul
copy /y lanthorn_icon.png dist\ >nul
copy /y lanthorn_icon.ico dist\ >nul

if not exist dist\projects mkdir dist\projects
copy /y Bazaar.csv     dist\projects\ >nul
copy /y Lanthorn.csv   dist\projects\ >nul
copy /y Iron_Waltz.csv dist\projects\ >nul

REM ---- Copy bundled ffmpeg into dist\ ----
if exist "tools\ffmpeg\ffmpeg.exe" (
    if not exist dist\ffmpeg mkdir dist\ffmpeg
    copy /y tools\ffmpeg\ffmpeg.exe  dist\ffmpeg\ >nul
    copy /y tools\ffmpeg\ffprobe.exe dist\ffmpeg\ >nul
    echo  Bundled ffmpeg into dist\ffmpeg\
)

echo.
echo  =============================================
echo    BUILD COMPLETE!
echo    Output: dist\LanthornPSG.exe
echo  =============================================
echo.

REM ---- Optionally build the NSIS installer ----
where makensis >nul 2>&1
if !errorlevel! == 0 (
    echo  NSIS found - building installer...
    makensis lanthorn_installer.nsi
    if exist "LanthornPSG_Setup_0.3.exe" (
        echo.
        echo  =============================================
        echo    INSTALLER CREATED: LanthornPSG_Setup_0.3.exe
        echo  =============================================
    ) else (
        echo  WARNING: NSIS ran but installer was not produced.
    )
) else (
    echo  NSIS not found - skipping installer step.
    echo  Install NSIS from https://nsis.sourceforge.io to enable installer builds.
)

echo.
pause
endlocal
