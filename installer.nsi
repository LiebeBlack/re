; MusikPlayer Installer Script
; NSIS installer for MusikPlayer

!define APPNAME "MusikPlayer"
!define COMPANYNAME "LiebeBlack"
!define DESCRIPTION "Modern music player with support for multiple audio formats"
!define VERSIONMAJOR 1
!define VERSIONMINOR 0
!define VERSIONBUILD 0
!define HELPURL "https://github.com/LiebeBlack/re"
!define UPDATEURL "https://github.com/LiebeBlack/re"
!define ABOUTURL "https://github.com/LiebeBlack/re"
!define INSTALLSIZE 50000

RequestExecutionLevel admin

!define OUTPUTFILE "MusikPlayer-Setup.exe"

OutFile "${OUTPUTFILE}"

InstallDir "$PROGRAMFILES\${APPNAME}"

Page directory
Page instfiles

Section "Install"
    SetOutPath $INSTDIR
    File /r "dist\MusikPlayer\*"
    
    ; Create uninstaller
    WriteUninstaller "$INSTDIR\uninstall.exe"
    
    ; Create desktop shortcut
    CreateShortCut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\MusikPlayer.exe" "" "$INSTDIR\MusikPlayer.exe" 0
    
    ; Create start menu shortcut
    CreateDirectory "$SMPROGRAMS\${APPNAME}"
    CreateShortCut "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" "$INSTDIR\MusikPlayer.exe" "" "$INSTDIR\MusikPlayer.exe" 0
    CreateShortCut "$SMPROGRAMS\${APPNAME}\Uninstall.lnk" "$INSTDIR\uninstall.exe"
    
    ; Register file associations
    WriteRegStr HKCR ".mp3" "" "MusikPlayer.mp3"
    WriteRegStr HKCR ".mp3" "Content Type" "audio/mpeg"
    WriteRegStr HKCR "MusikPlayer.mp3" "" "MP3 Audio File"
    WriteRegStr HKCR "MusikPlayer.mp3\DefaultIcon" "" "$INSTDIR\MusikPlayer.exe,0"
    WriteRegStr HKCR "MusikPlayer.mp3\shell\open\command" "" '"$INSTDIR\MusikPlayer.exe" "%1"'
    
    WriteRegStr HKCR ".wav" "" "MusikPlayer.wav"
    WriteRegStr HKCR ".wav" "Content Type" "audio/wav"
    WriteRegStr HKCR "MusikPlayer.wav" "" "WAV Audio File"
    WriteRegStr HKCR "MusikPlayer.wav\DefaultIcon" "" "$INSTDIR\MusikPlayer.exe,0"
    WriteRegStr HKCR "MusikPlayer.wav\shell\open\command" "" '"$INSTDIR\MusikPlayer.exe" "%1"'
    
    WriteRegStr HKCR ".ogg" "" "MusikPlayer.ogg"
    WriteRegStr HKCR ".ogg" "Content Type" "audio/ogg"
    WriteRegStr HKCR "MusikPlayer.ogg" "" "OGG Audio File"
    WriteRegStr HKCR "MusikPlayer.ogg\DefaultIcon" "" "$INSTDIR\MusikPlayer.exe,0"
    WriteRegStr HKCR "MusikPlayer.ogg\shell\open\command" "" '"$INSTDIR\MusikPlayer.exe" "%1"'
    
    WriteRegStr HKCR ".flac" "" "MusikPlayer.flac"
    WriteRegStr HKCR ".flac" "Content Type" "audio/flac"
    WriteRegStr HKCR "MusikPlayer.flac" "" "FLAC Audio File"
    WriteRegStr HKCR "MusikPlayer.flac\DefaultIcon" "" "$INSTDIR\MusikPlayer.exe,0"
    WriteRegStr HKCR "MusikPlayer.flac\shell\open\command" "" '"$INSTDIR\MusikPlayer.exe" "%1"'
    
    ; Add to Add/Remove Programs
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayName" "${APPNAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "UninstallString" "$INSTDIR\uninstall.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "QuietUninstallString" "$INSTDIR\uninstall.exe /S"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "Publisher" "${COMPANYNAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayVersion" "${VERSIONMAJOR}.${VERSIONMINOR}.${VERSIONBUILD}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "URLInfoAbout" "${ABOUTURL}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "HelpLink" "${HELPURL}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "URLUpdateInfo" "${UPDATEURL}"
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "VersionMajor" ${VERSIONMAJOR}
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "VersionMinor" ${VERSIONMINOR}
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "NoRepair" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "EstimatedSize" ${INSTALLSIZE}
SectionEnd

Section "Uninstall"
    Delete "$INSTDIR\uninstall.exe"
    RMDir /r "$INSTDIR"
    
    Delete "$DESKTOP\${APPNAME}.lnk"
    RMDir /r "$SMPROGRAMS\${APPNAME}"
    
    ; Remove file associations
    DeleteRegKey HKCR ".mp3"
    DeleteRegKey HKCR "MusikPlayer.mp3"
    DeleteRegKey HKCR ".wav"
    DeleteRegKey HKCR "MusikPlayer.wav"
    DeleteRegKey HKCR ".ogg"
    DeleteRegKey HKCR "MusikPlayer.ogg"
    DeleteRegKey HKCR ".flac"
    DeleteRegKey HKCR "MusikPlayer.flac"
    
    ; Remove from Add/Remove Programs
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"
SectionEnd
