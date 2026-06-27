param(
    [switch]$BuildOnly
)

$ErrorActionPreference = "Stop"

$ProjectDir = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectDir

$Python = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$Icon = Join-Path $ProjectDir "assets\jp-companion-icon.ico"
$BuiltExe = Join-Path $ProjectDir "dist\JP Companion\JP Companion.exe"
$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\JP Companion"

if (-not (Test-Path $Python)) {
    Write-Error "Missing project environment: $ProjectDir\.venv. Create it with: python -m venv .venv"
}

$pyinstallerArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--name", "JP Companion",
    "--collect-all", "unidic_lite"
)

if (Test-Path $Icon) {
    $pyinstallerArgs += @("--icon", $Icon, "--add-data", "$Icon;assets")
}

$pyinstallerArgs += "jp_companion.py"

& $Python @pyinstallerArgs

if (-not (Test-Path $BuiltExe)) {
    Write-Error "Build failed: $BuiltExe was not created."
}

Write-Host "Built: $BuiltExe"

if ($BuildOnly) {
    exit 0
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -Recurse -Force (Join-Path $ProjectDir "dist\JP Companion\*") $InstallDir

$InstalledExe = Join-Path $InstallDir "JP Companion.exe"
Start-Process $InstalledExe

foreach ($Path in @(
    (Join-Path $ProjectDir "build"),
    (Join-Path $ProjectDir "dist"),
    (Join-Path $ProjectDir "JP Companion.spec")
)) {
    if (Test-Path $Path) {
        Remove-Item -Recurse -Force $Path
    }
}
Write-Host "Installed and opened: $InstalledExe"
