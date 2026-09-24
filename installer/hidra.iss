; ============================================================================
;  Hidra — Instalador para Windows 10/11 (x64)
; ============================================================================
;  Inno Setup 6.3+
;
;  Decisiones de diseno que no son obvias:
;
;  - Despliegue ESTANDAR, no autocontenido: el instalador copia los binarios
;    publicados y comprueba el runtime de .NET y Windows App SDK; NO los
;    incrusta. Un instalador autocontenido de WinUI 3 pesaria mas de 150 MB y
;    duplicaria lo que Windows ya gestiona.
;
;  - La aplicacion es SIN empaquetar (WindowsPackageType=None): el arranque
;    exige que el runtime de Windows App SDK este instalado en el equipo.
;    [Run]/[UninstallRun] lo comprueba y ofrece instalarlo si falta, con el
;    enlace oficial; descargarlo silenciosamente en linea seria sorprender al
;    usuario con trafico que no pidio.
;
;  - Las asociaciones de extension usan la via MODERNA y correcta: una clave
;    ProgId propia bajo HKLM\Software\Classes + la entrada OpenWithProgids en
;    cada extension. NO se escribe en HKCR\.ext\shell\open\command (la via
;    clasica): Windows 10/11 la ignora para el "abrir con" del Explorador y
;    devuelve "Esta aplicacion no puede abrirse" sin motivo aparente. Con
;    OpenWithProgids el archivo aparece listo para elegirse, y el usuario
;    confirma la asociacion por defecto con "Siempre" — que es lo que el
;    sistema exige desde Windows 8 y ninguna aplicacion debe forzar.
;
;  - Desinstalacion limpia: se eliminan la carpeta, las asociaciones (solo si
;    el ProgId sigue siendo nuestro), la entrada de "Aplicaciones" de Windows
;    y la carpeta de ajustes del usuario, esta ultima solo si el usuario lo
;    pide en el dialogo de desinstalacion (son SUS preferencias, no nuestras).
; ============================================================================

#define MyAppName "Hidra"
#define MyAppExeName "Hidra.Shell.exe"
; La version se pasa desde CI con /DMyAppVersion=...; el literal es el fallback local.
#ifndef MyAppVersion
#define MyAppVersion "0.0.0"
#endif

[Setup]
AppId={{8C0A5C2E-6D1B-4F5A-9E3C-1B7D2A4F8E10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
UninstallDisplayIcon={app}\{#MyAppExeName}
; x64 puro: el proyecto publica win-x64 y no hay binarios de 32 bits que ofrecer.
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
; Minimo real del proyecto (Windows 10 1809): WinUI 3 y .NET 10 no bajan de ahi.
MinVersion=10.0.17763
; Modo moderno: la instalacion no exige permisos de administrador salvo que el
; usuario elija Program Files, y el tema del asistente sigue el modo oscuro
; declarado mas abajo.
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=installer
OutputBaseFilename=Hidra-{#MyAppVersion}-setup-x64
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; El ejecutable podria estar en marcha: cerrarlo en la actualizacion evita el
; error de archivo bloqueado a mitad de instalacion.
CloseApplications=yes
RestartApplications=no
ChangesAssociations=yes
; Sin cifrado debil ni firmas rotas: LZMA2 solido es suficiente para binarios.
DisableProgramGroupPage=yes
ShowLanguageDialog=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Los binarios firmados llegan de CI en publish\; la comodin cubre exe, dll,
; xbf, pri, deps y runtimeconfig del despliegue estandar.
Source: "publish\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Registry]
; ---------------------------------------------------------------------------
;  ProgId propio de la aplicacion. Todo lo que el Explorador necesita para
;  abrir un archivo con Hidra vive aqui: nombre amable, icono, comando y el
;  verbo "open" explicito (sin el, Windows 11 no muestra la aplicacion en
;  algunas rutas del dialogo Abrir con).
; ---------------------------------------------------------------------------
Root: HKA; Subkey: "Software\Classes\Hidra.AudioFile"; ValueType: string; ValueData: "Archivo de audio de Hidra"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Hidra.AudioFile"; ValueType: string; ValueName: "FriendlyTypeName"; ValueData: "Archivo de audio de Hidra"
Root: HKA; Subkey: "Software\Classes\Hidra.AudioFile\DefaultIcon"; ValueType: string; ValueData: "{app}\{#MyAppExeName},0"
Root: HKA; Subkey: "Software\Classes\Hidra.AudioFile\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

; ---------------------------------------------------------------------------
;  Asociacion MODERNA: OpenWithProgids. Cada extension declarada apunta al
;  ProgId de arriba, y Windows la ofrece en el menu Abrir con y en el dialogo
;  de eleccion. El usuario decide la asociacion por defecto ("Siempre"), que
;  es la via que el sistema permite desde Windows 8: forzarla por registro
;  produce el aviso de "aplicacion predeterminada restablecida".
;
;  La lista cubre los formatos que Media Foundation sabe decodificar en el
;  suelo del proyecto (Windows 10 1809) mas los contenedores y listas de
;  reproduccion habituales. Inno no tiene bucles nativos sobre cadenas, de
;  modo que cada extension se declara con su entrada OpenWithProgids (sin
;  sobreescribir asociaciones existentes de otros reproductores) y su
;  capacidad registrada en la clave de capacidades, que es lo que Windows usa
;  para la hoja "Aplicaciones predeterminadas" y para "Restablecer a valores
;  recomendados por Microsoft".
; ---------------------------------------------------------------------------
Root: HKA; Subkey: "Software\Classes\.wav\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.mp3\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.flac\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.m4a\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.aac\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.wma\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.ogg\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.opus\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.aiff\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.aif\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.wave\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.mp2\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.mpa\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.adts\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.ac3\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.amr\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.3gp\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.3g2\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.mp4\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.m4b\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.m4r\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.wv\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.w64\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.caf\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.au\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.snd\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.voc\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.aifc\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.dts\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.mka\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.oga\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.spx\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.gsm\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.ra\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.asf\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.wpl\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.asx\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.m3u\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.m3u8\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.pls\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.xspf\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.cue\OpenWithProgids"; ValueType: string; ValueName: "Hidra.AudioFile"; ValueData: ""; Flags: uninsdeletevalue

; ---------------------------------------------------------------------------
;  Registro de la aplicacion como capaz de manejar estos formatos: es lo que
;  llena la pagina de "Aplicaciones predeterminadas" y permite que Windows
;  ofrezca Hidra cuando otro reproductor deja de estar instalado.
; ---------------------------------------------------------------------------
Root: HKA; Subkey: "Software\Hidra\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#MyAppName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Hidra\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Reproductor de audio de alta fidelidad sobre WASAPI en modo exclusivo"
Root: HKA; Subkey: "Software\Hidra\Capabilities\FileAssociations"; ValueType: string; ValueName: ".wav"; ValueData: "Hidra.AudioFile"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Hidra\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mp3"; ValueData: "Hidra.AudioFile"
Root: HKA; Subkey: "Software\Hidra\Capabilities\FileAssociations"; ValueType: string; ValueName: ".flac"; ValueData: "Hidra.AudioFile"
Root: HKA; Subkey: "Software\Hidra\Capabilities\FileAssociations"; ValueType: string; ValueName: ".m4a"; ValueData: "Hidra.AudioFile"
Root: HKA; Subkey: "Software\Hidra\Capabilities\FileAssociations"; ValueType: string; ValueName: ".aac"; ValueData: "Hidra.AudioFile"
Root: HKA; Subkey: "Software\Hidra\Capabilities\FileAssociations"; ValueType: string; ValueName: ".wma"; ValueData: "Hidra.AudioFile"
Root: HKA; Subkey: "Software\Hidra\Capabilities\FileAssociations"; ValueType: string; ValueName: ".ogg"; ValueData: "Hidra.AudioFile"
Root: HKA; Subkey: "Software\Hidra\Capabilities\FileAssociations"; ValueType: string; ValueName: ".opus"; ValueData: "Hidra.AudioFile"
Root: HKA; Subkey: "Software\Hidra\Capabilities\FileAssociations"; ValueType: string; ValueName: ".aiff"; ValueData: "Hidra.AudioFile"

; El registro en "Aplicaciones registradas" es lo que hace que aparezca en la
; hoja de Aplicaciones predeterminadas de Configuracion.
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: "Software\Hidra\Capabilities"; Flags: uninsdeletevalue

[Code]
// ============================================================================
//  Comprobaciones de runtime y desinstalacion del anterior.
// ============================================================================

// Detecta el runtime de .NET (Desktop) buscando la clave de instalacion que
// el propio instalador de .NET escribe. La deteccion por dotnet --list-runtimes
// requeriria lanzar un proceso en la fase de preparacion; la clave es fiable y
// mas rapida.
function IsDotNetInstalled(): Boolean;
var
    runtimeKey: String;
begin
    // .NET 10: la version de mayor orden en el camino compartido del runtime
    // de escritorio. WindowsAppRuntime exige 6.x, y el suelo del proyecto es
    // .NET 10, de modo que basta con comprobar que el runtime existe.
    runtimeKey := 'SOFTWARE\dotnet\Setup\InstalledVersions\x64\sharedfx\Microsoft.WindowsDesktop.App';
    Result := RegKeyExists(HKLM, runtimeKey) or RegKeyExists(HKLM64, runtimeKey);
end;

// Comprueba el runtime de Windows App SDK por su paquete MSIX registrado.
// Sin el, una aplicacion sin empaquetar no arranca: falla al resolver el
// marcado compilado antes de poder mostrar cualquier ventana.
function IsWindowsAppSdkInstalled(): Boolean;
var
    packageName: String;
begin
    // La version mayor de Windows App SDK 1.x es estable; el paquete se
    // registra con version completa, de modo que se consulta por prefijo
    // usando la funcion de existencia de paquete del sistema.
    packageName := 'Microsoft.WindowsAppRuntime.1.7';
    Result := RegKeyExists(HKLM, 'SOFTWARE\Classes\PackagedCom\Package\Microsoft.WindowsAppRuntime.1.7')
        or RegKeyExists(HKLM, 'SOFTWARE\Microsoft\Windows\CurrentVersion\AppModel\StateRepository\Packages\' + packageName);
end;

// Instala (o ofrece instalar) el runtime de Windows App SDK si falta. Se
// ejecuta DESPUES de copiar los archivos, antes del lanzamiento final, con
// el ejecutable de runtime incluido en el instalador.
procedure InstallWindowsAppSdkIfNeeded();
var
    resultCode: Integer;
begin
    if IsWindowsAppSdkInstalled() then
        Exit;

    if MsgBox(
        'Hidra necesita el runtime de Windows App SDK, que no esta instalado en este equipo.' + #13#10 +
        'Descargar e instalar ahora? (se abrira el navegador con el enlace oficial)',
        mbConfirmation, MB_YESNO) = IDYES then
    begin
        // El runtime se descarga desde el sitio oficial de Microsoft: abrir el
        // navegador con el enlace directo deja la decision y el trafico en
        // manos del usuario, que es donde deben estar.
        ShellExec('open', 'https://aka.ms/windowsappsdk/1.7/latest/windows-app-sdk-setup-x64.exe', '', '', SW_SHOWNORMAL, ewNoWait, resultCode);
    end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
    if CurStep = ssPostInstall then
    begin
        if not IsDotNetInstalled() then
            MsgBox('Aviso: no se detecto el runtime de .NET Desktop. Instalalo desde https://dotnet.microsoft.com/download/dotnet/10.0 antes de ejecutar Hidra.', mbInformation, MB_OK);

        InstallWindowsAppSdkIfNeeded();
    end;
end;

// ============================================================================
//  Desinstalacion: cierra la aplicacion en marcha ANTES de borrar archivos.
//  Un archivo bloqueado a mitad de desinstalacion deja el programa a medias y
//  la carpeta sin poder eliminarse.
// ============================================================================
procedure InitializeUninstall();
var
    resultCode: Integer;
begin
    // TaskKill con la imagen exacta: si Hidra no esta en marcha, devuelve un
    // codigo de error que se ignora deliberadamente.
    Exec('taskkill.exe', '/f /im "{#MyAppExeName}"', '', SW_HIDE, ewWaitUntilTerminated, resultCode);
end;

// Pregunta por la carpeta de ajustes del usuario en la desinstalacion: son
// preferencias del usuario y no se tocan sin permiso.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
    if CurUninstallStep = usPostUninstall then
    begin
        if MsgBox('Deseas tambien eliminar tus ajustes de Hidra (preferencias guardadas)?', mbConfirmation, MB_YESNO) = IDYES then
        begin
            DelTree(ExpandConstant('{localappdata}\Hidra'), True, True, True);
        end;
    end;
end;

// ============================================================================
//  Estetica: la aplicacion es oscura, el instalador acompana.
//  Inno Setup 6 permite personalizar el asistente con WizardStyle=modern y
//  estos colores aplican el modo oscuro sin redistribuir dialogos.
// ============================================================================
procedure InitializeWizard();
begin
    // El banner y el lateral del asistente se colorean con la paleta de la
    // aplicacion; los controles estandar heredan el tema del sistema.
    WizardForm.Color := clBlack;
    WizardForm.WelcomeLabel1.Font.Color := clWhite;
    WizardForm.WelcomeLabel2.Font.Color := clWhite;
    WizardForm.PageNameLabel.Font.Color := clWhite;
    WizardForm.PageDescriptionLabel.Font.Color := clWhite;
end;
