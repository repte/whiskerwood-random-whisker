param(
    [Parameter(Mandatory)][string]$PackageDirectory,
    [string]$ModsRoot = (Join-Path $env:LOCALAPPDATA 'Whiskerwood\Saved\mods'),
    [switch]$Replace
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (@(Get-Process -Name '*Whiskerwood*' -ErrorAction SilentlyContinue).Count) {
    throw 'Close Whiskerwood before installing RandomWhisker. The game is not stopped automatically.'
}
$package = (Resolve-Path -LiteralPath $PackageDirectory).Path
$files = @(Get-ChildItem -LiteralPath $package -Force)
if ($files.Count -ne 2 -or @($files | Where-Object { $_.PSIsContainer -or $_.Name -cnotin @('RandomWhisker.pak', 'RandomWhisker.uplugin') }).Count) {
    throw 'The package directory must contain exactly RandomWhisker.pak and RandomWhisker.uplugin.'
}
$mod = Get-Content -LiteralPath (Join-Path $package 'RandomWhisker.uplugin') -Raw | ConvertFrom-Json
if ($mod.Name -cne 'RandomWhisker' -or $mod.EngineVersion -cne '5.8') { throw 'Invalid RandomWhisker descriptor.' }
$destination = Join-Path $ModsRoot 'RandomWhisker'
if ((Test-Path -LiteralPath $destination) -and -not $Replace) { throw "Already installed: $destination (use -Replace)" }
[void](New-Item -ItemType Directory -Path $destination -Force)
foreach ($name in @('RandomWhisker.pak', 'RandomWhisker.uplugin')) {
    Copy-Item -LiteralPath (Join-Path $package $name) -Destination (Join-Path $destination $name) -Force
    if ((Get-FileHash -LiteralPath (Join-Path $package $name)).Hash -cne (Get-FileHash -LiteralPath (Join-Path $destination $name)).Hash) {
        throw "Installed copy hash mismatch: $name"
    }
}
Write-Output "RANDOMWHISKER_LOCAL_INSTALL_PASS: $destination"
