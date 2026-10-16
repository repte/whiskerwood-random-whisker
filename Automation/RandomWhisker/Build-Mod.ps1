param(
    [string]$EngineRoot = 'D:\WWEngine',
    [string]$ProjectRoot = '',
    [switch]$UseGeneratedAssets
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
if (-not $ProjectRoot) { $ProjectRoot = Join-Path (Split-Path $repository -Parent) 'Modkit' }
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$editor = Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
$ubt = Join-Path $EngineRoot 'Engine\Build\BatchFiles\Build.bat'
$uat = Join-Path $EngineRoot 'Engine\Build\BatchFiles\RunUAT.bat'
$unrealPak = Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealPak.exe'
$project = Join-Path $ProjectRoot 'Whiskerwood.uproject'
$metadataPath = Join-Path $ProjectRoot 'Saved\RandomWhisker-PackageSetup.json'
$repositoryContent = Join-Path $repository 'Content\Mods\RandomWhisker'
$descriptor = Join-Path $repositoryContent 'RandomWhisker.uplugin'
$targetContent = Join-Path $ProjectRoot 'Content\Mods\RandomWhisker'
$sourceDescriptor = Join-Path $targetContent 'RandomWhisker.uplugin'
$pluginSource = Join-Path $repository 'Plugins\RandomWhiskerEditor'
$pluginTarget = Join-Path $ProjectRoot 'Plugins\RandomWhiskerEditor'
$expected = @('BP_MapLoad', 'WBP_RandomWhisker')
$assetFiles = @('BP_MapLoad.uasset', 'WBP_RandomWhisker.uasset', 'PAL_RandomWhisker.uasset')
foreach ($required in @($editor, $ubt, $uat, $unrealPak, $project, $descriptor,
        (Join-Path $PSScriptRoot 'generator.py'), (Join-Path $PSScriptRoot 'generate_ui.py'),
        (Join-Path $PSScriptRoot 'prepare_package.py'), (Join-Path $PSScriptRoot 'test_public.py'),
        (Join-Path $pluginSource 'RandomWhiskerEditor.uplugin'))) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Required file missing: $required" }
}
$mod = Get-Content -LiteralPath $descriptor -Raw | ConvertFrom-Json
if ($mod.Name -cne 'RandomWhisker' -or $mod.Version -cne '0.1.0' -or $mod.EngineVersion -cne '5.8') {
    throw 'Unexpected RandomWhisker descriptor identity, version, or engine'
}
if (@(Get-Process -Name '*Whiskerwood*', '*UnrealEditor*' -ErrorAction SilentlyContinue).Count) {
    throw 'Close Whiskerwood and the editor before building.'
}

$id = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$output = Join-Path $ProjectRoot "Saved\RandomWhiskerBuilds\$id"
$logs = Join-Path $output 'Logs'
[void](New-Item -ItemType Directory -Path $logs -Force)
$errorPattern = '(?im)\b(?:Error|Fatal):|\bBUILD FAILED\b|Traceback \(most recent call last\):|Assertion failed:|Fatal error:|AutomationTool exiting with ExitCode=[1-9]'

# Editor-only authoring helper: copy only its descriptor and sources, then compile the editor target.
foreach ($file in Get-ChildItem -LiteralPath $pluginSource -Recurse -File) {
    $relative = $file.FullName.Substring($pluginSource.Length).TrimStart('\')
    if ($relative -notmatch '^(RandomWhiskerEditor\.uplugin|Source\\)') { continue }
    $destination = Join-Path $pluginTarget $relative
    [void](New-Item -ItemType Directory -Path (Split-Path $destination -Parent) -Force)
    Copy-Item -LiteralPath $file.FullName -Destination $destination -Force
}
$compileLog = Join-Path $logs 'EditorCompile.log'
& $ubt WhiskerwoodEditor Win64 Development ("-Project=$project") -WaitMutex -NoHotReloadFromIDE *> $compileLog
if ($LASTEXITCODE -ne 0) { throw "Editor helper compile failed: $compileLog" }

if (-not $UseGeneratedAssets) {
    [void](New-Item -ItemType Directory -Path $targetContent -Force)
    foreach ($name in $assetFiles + @('RandomWhisker.uplugin')) {
        $source = Join-Path $repositoryContent $name
        if (Test-Path -LiteralPath $source -PathType Leaf) {
            Copy-Item -LiteralPath $source -Destination (Join-Path $targetContent $name) -Force
        }
    }
}

function Invoke-EditorScript {
    param([string]$Script, [string]$Marker)
    $log = Join-Path $logs "$Script.log"
    $console = Join-Path $logs "$Script-console.log"
    & $editor $project ("-ExecutePythonScript=" + (Join-Path $PSScriptRoot $Script)) `
        -unattended -nullrhi -nosound -culture=en ("-abslog=$log") -stdout -FullStdOutLogOutput *> $console
    if ($LASTEXITCODE -ne 0) { throw "RandomWhisker editor step failed: $console" }
    if (-not (Test-Path -LiteralPath $log -PathType Leaf)) { throw "Editor log missing: $log" }
    $text = (Get-Content -LiteralPath $log -Raw) + "`n" + (Get-Content -LiteralPath $console -Raw)
    if ($text -match $errorPattern -or $text -notmatch ([regex]::Escape($Marker))) {
        throw "RandomWhisker editor step not verified: $log"
    }
}

if (-not $UseGeneratedAssets) { Invoke-EditorScript -Script 'generator.py' -Marker 'RANDOMWHISKER_GENERATED_PASS' }
Invoke-EditorScript -Script 'test_public.py' -Marker 'RANDOMWHISKER_PUBLIC_TESTS_PASS'
if ((Get-FileHash -LiteralPath $descriptor -Algorithm SHA256).Hash -cne (Get-FileHash -LiteralPath $sourceDescriptor -Algorithm SHA256).Hash) {
    throw 'Modkit descriptor does not match the release descriptor'
}
$setupStarted = [DateTime]::UtcNow
Invoke-EditorScript -Script 'prepare_package.py' -Marker 'RANDOMWHISKER_PACKAGE_SETUP_PASS'
if (-not (Test-Path -LiteralPath $metadataPath -PathType Leaf) -or (Get-Item -LiteralPath $metadataPath).LastWriteTimeUtc -lt $setupStarted) {
    throw "Fresh RandomWhisker package metadata missing: $metadataPath"
}
$setup = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
$chunk = 0
if ($setup.mod -cne 'RandomWhisker' -or $setup.version -cne $mod.Version -or
        -not [int]::TryParse([string]$setup.chunk, [ref]$chunk) -or $chunk -lt 1 -or $chunk -gt 300 -or
        @(Compare-Object -ReferenceObject $expected -DifferenceObject @($setup.runtime_assets) -CaseSensitive).Count) {
    throw 'Invalid RandomWhisker chunk metadata'
}
Copy-Item -LiteralPath $metadataPath -Destination (Join-Path $output 'RandomWhisker-PackageSetup.json')

$cookLog = Join-Path $logs 'BuildCookRun.log'
& $uat BuildCookRun ("-project=$project") -platform=Win64 -clientconfig=Shipping `
    -build -cook -stage -pak -archive ("-archivedirectory=$output") `
    -nocompileeditor -installed -nop4 -utf8output -unattended -WaitForUATMutex *> $cookLog
if ($LASTEXITCODE -ne 0) { throw "RandomWhisker cook/package failed: $cookLog" }
$cookText = Get-Content -LiteralPath $cookLog -Raw
if ($cookText -notmatch 'BUILD SUCCESSFUL' -or $cookText -match $errorPattern) { throw "RandomWhisker cook not verified: $cookLog" }
$pak = Join-Path $output "Windows\Whiskerwood\Content\Paks\pakchunk$chunk-Windows.pak"
if (-not (Test-Path -LiteralPath $pak -PathType Leaf)) { throw "RandomWhisker chunk pak missing: $pak" }
$csv = Join-Path $logs 'RandomWhisker-Pak.csv'
$listLog = Join-Path $logs 'RandomWhisker-Pak-list.log'
& $unrealPak $pak -List -ExtractToMountPoint ("-CSV=$csv") -unattended *> $listLog
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $csv -PathType Leaf)) { throw "Pak listing failed: $listLog" }
$lines = @(Get-Content -LiteralPath $csv)
$entries = @($lines | Select-Object -Skip 1 | ConvertFrom-Csv -Header Filename,Offset,Size,Hash,Deleted,Compressed,CompressionMethod)
$assets = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
foreach ($entry in $entries) {
    $path = [string]$entry.Filename
    if ($path -cnotmatch '^\.\./\.\./\.\./Whiskerwood/Content/Mods/RandomWhisker/([A-Za-z0-9_]+)\.(uasset|uexp|ubulk|uptnl)$') {
        throw "File outside the RandomWhisker runtime boundary: $path"
    }
    if ($Matches[1] -cnotin $expected) { throw "Unexpected RandomWhisker asset: $path" }
    if ($Matches[2] -ceq 'uasset') { [void]$assets.Add($Matches[1]) }
}
foreach ($name in $expected) { if (-not $assets.Contains($name)) { throw "Missing cooked asset: $name" } }
$integrityLog = Join-Path $logs 'RandomWhisker-Pak-integrity.log'
& $unrealPak $pak -Verify -unattended *> $integrityLog
if ($LASTEXITCODE -ne 0 -or (Get-Content -LiteralPath $integrityLog -Raw) -notmatch 'Pak file .* healthy') { throw "Pak integrity failed: $integrityLog" }

$delivery = Join-Path $output 'Delivery\RandomWhisker'
[void](New-Item -ItemType Directory -Path $delivery)
Copy-Item -LiteralPath $pak -Destination (Join-Path $delivery 'RandomWhisker.pak')
Copy-Item -LiteralPath $descriptor -Destination (Join-Path $delivery 'RandomWhisker.uplugin')
[pscustomobject]@{
    Result = 'RANDOMWHISKER_PACKAGE_CHECKS_PASS'; Version = $mod.Version; Chunk = $chunk; Assets = $expected
    Entries = $entries.Count; Bytes = (Get-Item -LiteralPath $pak).Length
    SHA256 = (Get-FileHash -LiteralPath $pak -Algorithm SHA256).Hash; RuntimeValidated = $false
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $output 'package-verification.json') -Encoding utf8
foreach ($name in $assetFiles) {
    Copy-Item -LiteralPath (Join-Path $targetContent $name) -Destination (Join-Path $repositoryContent $name) -Force
}
Write-Output "RANDOMWHISKER_BUILD_PASS: $delivery"
