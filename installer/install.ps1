<#
.SYNOPSIS
  EmbedCo installer for Windows.

.DESCRIPTION
  Installs arduino-cli (for board compile/upload) and EmbedCo Python dependencies.

.PARAMETER Prefix
  Directory to install arduino-cli.exe into (default: $env:LOCALAPPDATA\EmbedCo\bin).

.PARAMETER ProjectDir
  EmbedCo project directory containing requirements.txt (default: repo root).

.PARAMETER SkipArduinoCli
  Skip installing arduino-cli.

.PARAMETER SkipPythonDeps
  Skip installing Python dependencies.

.EXAMPLE
  .\installer\install.ps1

.EXAMPLE
  .\installer\install.ps1 -Prefix "$env:USERPROFILE\.local\bin" -SkipArduinoCli
#>

[CmdletBinding()]
param(
  [string]$Prefix = (Join-Path $env:LOCALAPPDATA "EmbedCo\bin"),
  [string]$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [switch]$SkipArduinoCli,
  [switch]$SkipPythonDeps
)

$ErrorActionPreference = "Stop"

function Write-Log($msg) { Write-Host "[embedco-install] $msg" }
function Write-Warn($msg) { Write-Warning "[embedco-install] $msg" }
function Fail($msg) { throw "[embedco-install] $msg" }

function Add-ToUserPath([string]$dir) {
  $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
  $parts = @()
  if ($userPath) { $parts = $userPath -split ";" | Where-Object { $_ -and $_.Trim() -ne "" } }
  $normalized = $dir.TrimEnd("\")
  foreach ($p in $parts) { if ($p.TrimEnd("\") -ieq $normalized) { return $false } }
  $newPath = if ($userPath) { "$userPath;$normalized" } else { $normalized }
  [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
  $env:Path = "$env:Path;$normalized"
  return $true
}

function Get-PythonCmd {
  $candidates = @(
    @("py", @("-3")),
    @("python", @()),
    @("python3", @())
  )
  foreach ($c in $candidates) {
    $cmd = Get-Command $c[0] -ErrorAction SilentlyContinue
    if ($cmd) { return @{ Exe = $c[0]; Args = $c[1] } }
  }
  return $null
}

function Install-ArduinoCli {
  Write-Log "Installing arduino-cli to $Prefix..."
  New-Item -ItemType Directory -Force -Path $Prefix | Out-Null

  $arch = $env:PROCESSOR_ARCHITECTURE
  if ($arch -eq "ARM64") {
    $url = "https://downloads.arduino.cc/arduino-cli/arduino-cli_latest_Windows_ARM64.zip"
  } else {
    $url = "https://downloads.arduino.cc/arduino-cli/arduino-cli_latest_Windows_64bit.zip"
  }

  $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("embedco-arduino-cli-" + [Guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Force -Path $tmp | Out-Null
  $zip = Join-Path $tmp "arduino-cli.zip"
  try {
    Write-Log "Downloading $url"
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    $exe = Get-ChildItem -Path $tmp -Recurse -Filter "arduino-cli.exe" | Select-Object -First 1
    if (-not $exe) { Fail "arduino-cli.exe not found in downloaded archive." }
    Copy-Item -Path $exe.FullName -Destination (Join-Path $Prefix "arduino-cli.exe") -Force
  } finally {
    Remove-Item -Recurse -Force -Path $tmp -ErrorAction SilentlyContinue
  }

  $added = Add-ToUserPath $Prefix
  if ($added) {
    Write-Log "Added $Prefix to user PATH (restart your terminal for new sessions)."
  } else {
    Write-Log "$Prefix is already in PATH."
  }

  $cli = Join-Path $Prefix "arduino-cli.exe"
  if (Test-Path $cli) {
    try { & $cli version } catch { }
    Write-Log "arduino-cli installed at $cli"
  } else {
    Fail "arduino-cli installation did not complete successfully."
  }
}

function Install-PythonDeps {
  $py = Get-PythonCmd
  if (-not $py) { Fail "Python 3 was not found. Install Python 3.8+ (https://www.python.org/downloads/) and ensure it is on PATH." }

  $verArgs = @()
  if ($py.Args) { $verArgs += $py.Args }
  $verArgs += @("-c", "import sys; raise SystemExit(0 if sys.version_info >= (3,8) else 1)")
  & $py.Exe @verArgs
  if ($LASTEXITCODE -ne 0) { Fail "Python 3.8+ is required." }

  $req = Join-Path $ProjectDir "requirements.txt"
  if (-not (Test-Path $req)) { Fail "requirements.txt not found in $ProjectDir" }

  Write-Log "Installing EmbedCo Python dependencies from $req..."
  $pipArgs = @()
  if ($py.Args) { $pipArgs += $py.Args }
  $pipArgs += @("-m", "pip", "install", "-r", $req)
  & $py.Exe @pipArgs
  if ($LASTEXITCODE -ne 0) { Fail "pip install failed." }
  Write-Log "Python dependencies installed."
}

if (-not (Test-Path $ProjectDir)) { Fail "Project directory not found: $ProjectDir" }

Write-Log "EmbedCo installer (Windows)"
Write-Log "Project directory: $ProjectDir"

if (-not $SkipArduinoCli) {
  Install-ArduinoCli
} else {
  Write-Log "Skipping arduino-cli installation (-SkipArduinoCli)."
}

if (-not $SkipPythonDeps) {
  Install-PythonDeps
} else {
  Write-Log "Skipping Python dependency installation (-SkipPythonDeps)."
}

Write-Log "Done."
Write-Log "To start EmbedCo, run from the project directory:"
Write-Log "  python server.py"
if (-not $SkipArduinoCli) {
  Write-Log "If 'arduino-cli' is not recognized, restart your terminal so PATH updates take effect."
}
