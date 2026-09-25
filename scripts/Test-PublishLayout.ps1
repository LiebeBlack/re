<#
.SYNOPSIS
    Verifica que la publicacion de Hidra.Shell contiene los archivos sin los
    cuales el ejecutable no arranca, y resume el tamano del despliegue.

.DESCRIPTION
    El publicador de una aplicacion WinUI 3 sin empaquetar omite el marcado
    compilado (.xbf) y el indice de recursos (.pri) cuando algo va mal en la
    compilacion, y el ejecutable resultante falla al arranque sin decir por
    que. La comprobacion vive en un script compartido para que build.yml y
    release.yml juzguen la publicacion con la MISMA lista y no se desincronicen.

.PARAMETER PublishDir
    Carpeta de salida de `dotnet publish` a inspeccionar.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string] $PublishDir
)

$required = @(
    'Hidra.Shell.exe',
    'Hidra.Shell.dll',
    'Hidra.Kernel.dll',
    'Hidra.Audio.dll',
    'Hidra.Interop.dll',
    'Hidra.Shell.pri',
    'App.xbf',
    'MainWindow.xbf',
    'EngineSettingsPage.xbf',
    'DiagnosticsPage.xbf',
    'AboutPage.xbf',
    'Hidra.Shell.deps.json',
    'Hidra.Shell.runtimeconfig.json'
)

$missing = $required | Where-Object { -not (Test-Path (Join-Path $PublishDir $_)) }
if ($missing) {
    throw "Faltan archivos en la publicacion: $($missing -join ', ')"
}

$files = Get-ChildItem $PublishDir -File
$own = $files | Where-Object { $_.Name -like 'Hidra.*' } | Measure-Object -Property Length -Sum

Write-Host ("Binarios propios: {0} archivos, {1:N0} KB" -f $own.Count, ($own.Sum / 1KB))
Write-Host ("Total publicado : {0} archivos" -f $files.Count)
