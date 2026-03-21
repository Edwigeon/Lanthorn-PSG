; ============================================================
; Lanthorn PSG v0.3 — NSIS Windows Installer Script
; Requires: NSIS 3.x (https://nsis.sourceforge.io)
; Run AFTER build.bat has produced the dist\ folder.
; Usage: makensis lanthorn_installer.nsi
; Output: LanthornPSG_Setup_0.3.exe
; ============================================================

Unicode True

!include "MUI2.nsh"
!include "FileFunc.nsh"

; -------- Metadata --------
!define APP_NAME        "Lanthorn PSG"
!define APP_VERSION     "0.3"
!define APP_PUBLISHER   "Lanthorn PSG"
!define APP_EXE         "LanthornPSG.exe"
!define APP_ICON        "lanthorn_icon.ico"
!define INSTALL_DIR     "$PROGRAMFILES64\${APP_NAME}"
!define UNINSTALL_KEY   "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
!define REG_KEY         "Software\${APP_NAME}"

Name            "${APP_NAME} ${APP_VERSION}"
OutFile         "LanthornPSG_Setup_${APP_VERSION}.exe"
InstallDir      "${INSTALL_DIR}"
InstallDirRegKey HKLM "${REG_KEY}" "InstallPath"
RequestExecutionLevel admin
BrandingText    "Lanthorn PSG v${APP_VERSION}"

; -------- MUI Settings --------
!define MUI_ICON        "${APP_ICON}"
!define MUI_UNICON      "${APP_ICON}"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Welcome to the ${APP_NAME} Installer"
!define MUI_WELCOMEPAGE_TEXT  "This will install ${APP_NAME} v${APP_VERSION} on your computer.$\r$\n$\r$\nClick Next to continue."
!define MUI_FINISHPAGE_RUN        "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT   "Launch ${APP_NAME} now"
!define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\ENGINE_SPEC.md"
!define MUI_FINISHPAGE_SHOWREADME_TEXT "View documentation"

; -------- Pages --------
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE    "dist\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; ============================================================
; INSTALLER SECTION
; ============================================================
Section "Install" SecMain

    SetOutPath "$INSTDIR"

    ; Main executable
    File "dist\${APP_EXE}"

    ; Data files alongside the executable
    File "dist\lanthorn_icon.png"
    File "dist\lanthorn_icon.ico"
    File "dist\ENGINE_SPEC.md"
    File "dist\LICENSE"

    ; Presets folder
    SetOutPath "$INSTDIR\presets"
    File /r "dist\presets\*.*"

    ; Demo projects
    SetOutPath "$INSTDIR\projects"
    File "dist\projects\Bazaar.csv"
    File "dist\projects\Lanthorn.csv"
    File "dist\projects\Iron_Waltz.csv"

    ; Bundled ffmpeg binaries (required by pydub for MP3 export)
    ; build.bat downloads these automatically into tools\ffmpeg\
    IfFileExists "dist\ffmpeg\ffmpeg.exe" 0 +3
        SetOutPath "$INSTDIR\ffmpeg"
        File "dist\ffmpeg\ffmpeg.exe"
    IfFileExists "dist\ffmpeg\ffprobe.exe" 0 +2
        File "dist\ffmpeg\ffprobe.exe"

    ; Write registry keys for uninstaller / Add/Remove Programs
    SetOutPath "$INSTDIR"
    WriteRegStr   HKLM "${REG_KEY}"        "InstallPath"   "$INSTDIR"
    WriteRegStr   HKLM "${UNINSTALL_KEY}"  "DisplayName"           "${APP_NAME}"
    WriteRegStr   HKLM "${UNINSTALL_KEY}"  "DisplayVersion"        "${APP_VERSION}"
    WriteRegStr   HKLM "${UNINSTALL_KEY}"  "Publisher"             "${APP_PUBLISHER}"
    WriteRegStr   HKLM "${UNINSTALL_KEY}"  "InstallLocation"       "$INSTDIR"
    WriteRegStr   HKLM "${UNINSTALL_KEY}"  "DisplayIcon"           "$INSTDIR\${APP_EXE}"
    WriteRegStr   HKLM "${UNINSTALL_KEY}"  "UninstallString"       "$INSTDIR\Uninstall.exe"
    WriteRegStr   HKLM "${UNINSTALL_KEY}"  "QuietUninstallString"  "$\"$INSTDIR\Uninstall.exe$\" /S"
    WriteRegDWORD HKLM "${UNINSTALL_KEY}"  "NoModify"              1
    WriteRegDWORD HKLM "${UNINSTALL_KEY}"  "NoRepair"              1

    ; Estimate installed size for Add/Remove Programs
    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    WriteRegDWORD HKLM "${UNINSTALL_KEY}" "EstimatedSize" $0

    ; Write the uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; Start Menu shortcuts
    CreateDirectory "$SMPROGRAMS\${APP_NAME}"
    CreateShortcut  "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" \
                    "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0
    CreateShortcut  "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk" \
                    "$INSTDIR\Uninstall.exe" "" "$INSTDIR\Uninstall.exe" 0

    ; Desktop shortcut
    CreateShortcut  "$DESKTOP\${APP_NAME}.lnk" \
                    "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0

SectionEnd

; ============================================================
; UNINSTALLER SECTION
; ============================================================
Section "Uninstall"

    ; Remove application files
    Delete "$INSTDIR\${APP_EXE}"
    Delete "$INSTDIR\lanthorn_icon.png"
    Delete "$INSTDIR\lanthorn_icon.ico"
    Delete "$INSTDIR\ENGINE_SPEC.md"
    Delete "$INSTDIR\LICENSE"
    Delete "$INSTDIR\Uninstall.exe"

    ; Remove presets, projects, and ffmpeg folders
    RMDir /r "$INSTDIR\presets"
    RMDir /r "$INSTDIR\projects"
    RMDir /r "$INSTDIR\ffmpeg"
    RMDir    "$INSTDIR"

    ; Remove shortcuts
    Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
    Delete "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk"
    RMDir  "$SMPROGRAMS\${APP_NAME}"
    Delete "$DESKTOP\${APP_NAME}.lnk"

    ; Remove registry keys
    DeleteRegKey HKLM "${UNINSTALL_KEY}"
    DeleteRegKey HKLM "${REG_KEY}"

SectionEnd
