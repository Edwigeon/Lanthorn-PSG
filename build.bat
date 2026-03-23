@echo off
REM ============================================================
REM Lanthorn PSG v0.3.3 - Windows Build Script
REM Run this from the lanthorn_psg directory after installing Python.
REM ============================================================

setlocal EnableDelayedExpansion

echo.
echo  ========================================
echo    Lanthorn PSG v0.3.3 - Build System
echo  ========================================
echo.
echo    1.  Portable          (single standalone .exe)
echo    2.  Installer         (Setup .exe via NSIS)
echo    3.  Both
echo.
set /p "BUILD_CHOICE=  Select option [1-3]: "

if "!BUILD_CHOICE!" == "3" goto :build_both
if "!BUILD_CHOICE!" == "2" goto :build_installer_flow
if "!BUILD_CHOICE!" == "1" goto :build_portable_flow

echo  Invalid choice.
pause
exit /b 1

REM ============================================================
:build_both
REM ============================================================
call :check_python
call :install_deps
call :fetch_ffmpeg
call :build_portable
call :build_exe
call :copy_support_files
call :build_installer
echo.
echo  =============================================
echo    ALL BUILDS COMPLETE!
echo    Portable:  dist\LanthornPSG_Portable.exe
echo    Installer: LanthornPSG_Setup_0.3.3.exe
echo  =============================================
goto :done

REM ============================================================
:build_portable_flow
REM ============================================================
call :check_python
call :install_deps
call :fetch_ffmpeg
call :build_portable
goto :done

REM ============================================================
:build_installer_flow
REM ============================================================
call :check_python
call :install_deps
call :fetch_ffmpeg
call :build_exe
call :copy_support_files
call :build_installer
goto :done

REM ============================================================
REM  SUBROUTINES
REM ============================================================

:check_python
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found. Install Python 3.12+ from python.org
    echo  Make sure "Add Python to PATH" is checked during install.
    pause
    exit /b 1
)
exit /b 0

:install_deps
echo.
echo  Installing Python dependencies...
python -m pip install -r requirements.txt
python -m pip install pyinstaller
exit /b 0

:fetch_ffmpeg
echo.
echo  Checking for bundled ffmpeg...
if not exist "tools\ffmpeg\ffmpeg.exe" (
    echo  Downloading ffmpeg...

    if not exist tools mkdir tools

    REM Try curl.exe first (built into Windows 10/11 - fast)
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
exit /b 0

:build_exe
echo.
echo  Cleaning build cache...
if exist build rmdir /s /q build
echo  Building executable...
python -m PyInstaller lanthorn_psg.spec --clean

if not exist "dist\LanthornPSG\LanthornPSG.exe" (
    echo.
    echo  BUILD FAILED - check errors above.
    pause
    exit /b 1
)
if exist build rmdir /s /q build
exit /b 0

:build_portable
echo.
echo  Cleaning build cache...
if exist build rmdir /s /q build
echo  Building portable executable (one-file)...
echo  This may take a few minutes...
python -m PyInstaller lanthorn_psg_portable.spec --clean

if not exist "dist\LanthornPSG_Portable.exe" (
    echo.
    echo  BUILD FAILED - check errors above.
    pause
    exit /b 1
)
echo.
echo  =============================================
echo    PORTABLE BUILD COMPLETE!
echo    Output: dist\LanthornPSG_Portable.exe
echo  =============================================
if exist build rmdir /s /q build
exit /b 0

:copy_support_files
echo.
echo  Copying supporting files into dist\LanthornPSG\...
if not exist dist\LanthornPSG\projects mkdir dist\LanthornPSG\projects
copy /y Bazaar.csv     dist\LanthornPSG\projects\ >nul
copy /y Lanthorn.csv   dist\LanthornPSG\projects\ >nul
copy /y Iron_Waltz.csv dist\LanthornPSG\projects\ >nul

if exist "tools\ffmpeg\ffmpeg.exe" (
    if not exist dist\LanthornPSG\ffmpeg mkdir dist\LanthornPSG\ffmpeg
    copy /y tools\ffmpeg\ffmpeg.exe  dist\LanthornPSG\ffmpeg\ >nul
    copy /y tools\ffmpeg\ffprobe.exe dist\LanthornPSG\ffmpeg\ >nul
    echo  Bundled ffmpeg into dist\LanthornPSG\ffmpeg\
)
exit /b 0

:build_installer
echo.
echo  Checking for NSIS...

set "MAKENSIS_CMD="

REM Check if makensis is already on PATH
where makensis >nul 2>&1
if !errorlevel! == 0 (
    set "MAKENSIS_CMD=makensis"
    echo  NSIS found on PATH.
    goto :run_nsis
)

REM Check standard install locations
if exist "C:\Program Files\NSIS\makensis.exe" (
    set "MAKENSIS_CMD=C:\Program Files\NSIS\makensis.exe"
    echo  NSIS found in Program Files.
    goto :run_nsis
)
set "NSIS_X86=C:\Program Files (x86)\NSIS\makensis.exe"
if exist "!NSIS_X86!" (
    set "MAKENSIS_CMD=!NSIS_X86!"
    echo  NSIS found in Program Files x86.
    goto :run_nsis
)

REM Check if we already downloaded it
if exist "tools\nsis\makensis.exe" (
    set "MAKENSIS_CMD=tools\nsis\makensis.exe"
    echo  NSIS found in tools\nsis\.
    goto :run_nsis
)

REM Download NSIS portable
echo  NSIS not found - downloading NSIS 3.10 portable...
if not exist tools mkdir tools

set "NSIS_URL=https://sourceforge.net/projects/nsis/files/NSIS 3/3.10/nsis-3.10.zip/download"

where curl.exe >nul 2>&1
if !errorlevel! == 0 (
    echo  Downloading with curl...
    curl.exe -L --progress-bar -o "tools\nsis_dl.zip" "!NSIS_URL!"
) else (
    echo  Downloading with PowerShell...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri '!NSIS_URL!' -OutFile 'tools\nsis_dl.zip' -UseBasicParsing"
)

if not exist "tools\nsis_dl.zip" (
    echo  WARNING: Failed to download NSIS. Skipping installer step.
    echo  Install NSIS manually from https://nsis.sourceforge.io
    exit /b 1
)

echo  Extracting NSIS...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path 'tools\nsis_dl.zip' -DestinationPath 'tools\nsis_tmp' -Force"

for /d %%D in (tools\nsis_tmp\nsis-*) do (
    if exist "%%D\makensis.exe" (
        if not exist "tools\nsis" mkdir tools\nsis
        xcopy /e /i /y "%%D\*" "tools\nsis\" >nul
    )
)

del /q tools\nsis_dl.zip 2>nul
rmdir /s /q tools\nsis_tmp 2>nul

if exist "tools\nsis\makensis.exe" (
    set "MAKENSIS_CMD=tools\nsis\makensis.exe"
    echo  NSIS downloaded successfully.
) else (
    echo  WARNING: Could not extract NSIS. Skipping installer step.
    exit /b 1
)

:run_nsis
echo  Building installer with NSIS...
"%MAKENSIS_CMD%" lanthorn_installer.nsi

if exist "LanthornPSG_Setup_0.3.3.exe" (
    echo.
    echo  =============================================
    echo    INSTALLER CREATED: LanthornPSG_Setup_0.3.3.exe
    echo  =============================================
) else (
    echo  WARNING: NSIS ran but installer was not produced.
)

REM Clean up intermediate build folder — installer is self-contained
if exist "dist\LanthornPSG" (
    echo  Cleaning up intermediate build files...
    rmdir /s /q "dist\LanthornPSG"
)
exit /b 0

:done
echo.
pause
endlocal
