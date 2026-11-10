<#
.SYNOPSIS
    EmbedCo Windows Installer

.DESCRIPTION
    Interactive installer for:
    - arduino-cli
    - Python dependencies
    - Arduino core index
    - Arduino AVR core

.PARAMETER Prefix
    Arduino CLI installation directory.

.PARAMETER ProjectDir
    EmbedCo project root.

.PARAMETER SkipArduinoCli
    Skip Arduino CLI installation by default.

.PARAMETER SkipPythonDeps
    Skip Python dependencies by default.

.PARAMETER NonInteractive
    Disable interactive menu.
#>

[CmdletBinding()]
param(
    [string]$Prefix = (Join-Path $env:LOCALAPPDATA "EmbedCo\bin"),
    [string]$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [switch]$SkipArduinoCli,
    [switch]$SkipPythonDeps,
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"

# --------------------------------------------------
# Logging
# --------------------------------------------------

function Write-Log($Message) {
    Write-Host "[EmbedCo] $Message" -ForegroundColor Cyan
}

function Write-Warn($Message) {
    Write-Warning "[EmbedCo] $Message"
}

function Fail($Message) {
    throw "[EmbedCo] $Message"
}

# --------------------------------------------------
# PATH MANAGEMENT
# --------------------------------------------------

function Add-ToUserPath([string]$Directory) {

    $Directory = $Directory.TrimEnd("\")

    $UserPath = [Environment]::GetEnvironmentVariable(
        "Path", "User"
    )

    $Parts = @()

    if ($UserPath) {
        $Parts = $UserPath -split ";" |
            Where-Object { $_.Trim() -ne "" }
    }

    foreach ($Part in $Parts) {
        if ($Part.TrimEnd("\") -ieq $Directory) {
            return $false
        }
    }

    $NewPath = if ($UserPath) {
        "$UserPath;$Directory"
    } else {
        $Directory
    }

    [Environment]::SetEnvironmentVariable(
        "Path", $NewPath, "User"
    )

    if ($env:Path -notlike "*$Directory*") {
        $env:Path += ";$Directory"
    }

    return $true
}

# --------------------------------------------------
# PYTHON DETECTION
# --------------------------------------------------

function Get-PythonCmd {

    $Candidates = @(
        [PSCustomObject]@{
            Exe = "py"
            Args = @("-3")
        },
        [PSCustomObject]@{
            Exe = "python"
            Args = @()
        },
        [PSCustomObject]@{
            Exe = "python3"
            Args = @()
        }
    )

    foreach ($Candidate in $Candidates) {

        $Command = Get-Command $Candidate.Exe `
            -ErrorAction SilentlyContinue

        if ($Command) {

            $VersionArgs = @()

            $VersionArgs += $Candidate.Args
            $VersionArgs += @("-c", "import sys; print(sys.version_info[:3])")

            try {
                & $Candidate.Exe @VersionArgs

                if ($LASTEXITCODE -eq 0) {
                    return $Candidate
                }
            }
            catch {
                continue
            }
        }
    }

    return $null
}

# --------------------------------------------------
# ARDUINO CLI DETECTION
# --------------------------------------------------

function Get-ArduinoCliPath {

    $LocalPath = Join-Path $Prefix "arduino-cli.exe"

    if (Test-Path $LocalPath) {
        return $LocalPath
    }

    $Command = Get-Command "arduino-cli" `
        -ErrorAction SilentlyContinue

    if ($Command) {
        return $Command.Source
    }

    return $null
}

# --------------------------------------------------
# ARDUINO CLI INSTALLATION
# --------------------------------------------------

function Install-ArduinoCli {

    Write-Log "Installing Arduino CLI..."

    New-Item -ItemType Directory `
        -Force -Path $Prefix | Out-Null

    $Architecture = $env:PROCESSOR_ARCHITECTURE

    if ($env:PROCESSOR_ARCHITEW6432) {
        $Architecture = $env:PROCESSOR_ARCHITEW6432
    }

    switch ($Architecture) {
        "ARM64" {
            $URL = "https://downloads.arduino.cc/arduino-cli/arduino-cli_latest_Windows_ARM64.zip"
        }
        default {
            $URL = "https://downloads.arduino.cc/arduino-cli/arduino-cli_latest_Windows_64bit.zip"
        }
    }

    $TempDir = Join-Path ([IO.Path]::GetTempPath()) (
        "embedco-" + [Guid]::NewGuid().ToString("N")
    )

    New-Item -ItemType Directory `
        -Force -Path $TempDir | Out-Null

    $ZipPath = Join-Path $TempDir "arduino-cli.zip"

    try {

        Write-Log "Downloading Arduino CLI..."

        Invoke-WebRequest `
            -Uri $URL `
            -OutFile $ZipPath `
            -ErrorAction Stop

        Expand-Archive `
            -Path $ZipPath `
            -DestinationPath $TempDir `
            -Force

        $Executable = Get-ChildItem `
            -Path $TempDir `
            -Recurse `
            -Filter "arduino-cli.exe" |
            Select-Object -First 1

        if (-not $Executable) {
            Fail "arduino-cli.exe missing from archive."
        }

        Copy-Item `
            $Executable.FullName `
            (Join-Path $Prefix "arduino-cli.exe") `
            -Force

    }
    finally {

        Remove-Item $TempDir `
            -Recurse -Force `
            -ErrorAction SilentlyContinue
    }

    Add-ToUserPath $Prefix | Out-Null

    $CLI = Join-Path $Prefix "arduino-cli.exe"

    if (-not (Test-Path $CLI)) {
        Fail "Arduino CLI installation failed."
    }

    & $CLI version

    if ($LASTEXITCODE -ne 0) {
        Fail "Arduino CLI verification failed."
    }

    Write-Log "Arduino CLI installed successfully."
}

# --------------------------------------------------
# PYTHON DEPENDENCIES
# --------------------------------------------------

function Install-PythonDeps {

    $Python = Get-PythonCmd

    if (-not $Python) {
        Fail "Python 3 was not found. Install Python 3.8 or newer."
    }

    Write-Log "Using Python: $($Python.Exe)"

    $VersionArgs = @()
    $VersionArgs += $Python.Args
    $VersionArgs += @(
        "-c",
        "import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)"
    )

    & $Python.Exe @VersionArgs

    if ($LASTEXITCODE -ne 0) {
        Fail "Python 3.8 or newer is required."
    }

    $Requirements = Join-Path $ProjectDir "requirements.txt"

    if (-not (Test-Path $Requirements)) {
        Fail "requirements.txt not found: $Requirements"
    }

    Write-Log "Installing Python dependencies..."

    $PipArgs = @()
    $PipArgs += $Python.Args
    $PipArgs += @(
        "-m", "pip", "install", "-r", $Requirements
    )

    & $Python.Exe @PipArgs

    if ($LASTEXITCODE -ne 0) {
        Fail "Python dependency installation failed."
    }

    Write-Log "Python dependencies installed."
}

# --------------------------------------------------
# ARDUINO CORE MANAGEMENT
# --------------------------------------------------

function Invoke-ArduinoCli([string[]]$Arguments) {

    $CLI = Get-ArduinoCliPath

    if (-not $CLI) {
        Fail "Arduino CLI not found."
    }

    Write-Log "Running: arduino-cli $($Arguments -join ' ')"

    & $CLI @Arguments

    if ($LASTEXITCODE -ne 0) {
        Fail "Arduino CLI command failed."
    }
}

function Update-CoreIndex {
    Invoke-ArduinoCli @("core", "update-index")
}

function Install-AvrCore {
    Invoke-ArduinoCli @("core", "install", "arduino:avr")
}

# --------------------------------------------------
# INTERACTIVE CHECKBOX MENU
# --------------------------------------------------

function Show-CheckboxMenu([array]$Items) {

    $Index = 0

    Write-Host ""
    Write-Host " EMBEDCO INSTALLER" -ForegroundColor Cyan
    Write-Host " Select components to install"
    Write-Host ""

    Write-Host " Up/Down = Navigate | Space = Toggle"
    Write-Host " A = Select all | N = Select none | Enter = Continue"
    Write-Host ""

    try {
        [Console]::CursorVisible = $false
    }
    catch {}

    try {

        $StartTop = [Console]::CursorTop

        while ($true) {

            [Console]::SetCursorPosition(0, $StartTop)

            for ($i = 0; $i -lt $Items.Count; $i++) {

                $Mark = if ($Items[$i].Selected) {
                    "X"
                } else {
                    " "
                }

                $Pointer = if ($i -eq $Index) {
                    ">"
                } else {
                    " "
                }

                $Line = "$Pointer [$Mark] $($Items[$i].Label)"

                Write-Host $Line.PadRight(
                    [Math]::Max(1, [Console]::WindowWidth - 1)
                )
            }

            Write-Host ""

            $Key = [Console]::ReadKey($true)

            switch ($Key.Key) {

                "UpArrow" {
                    if ($Index -gt 0) {
                        $Index--
                    }
                }

                "DownArrow" {
                    if ($Index -lt $Items.Count - 1) {
                        $Index++
                    }
                }

                "Spacebar" {
                    $Items[$Index].Selected =
                        -not $Items[$Index].Selected
                }

                "A" {
                    foreach ($Item in $Items) {
                        $Item.Selected = $true
                    }
                }

                "N" {
                    foreach ($Item in $Items) {
                        $Item.Selected = $false
                    }
                }

                "Enter" {
                    break
                }
            }

            if ($Key.Key -eq "Enter") {
                break
            }
        }
    }
    finally {

        try {
            [Console]::CursorVisible = $true
        }
        catch {}

        Write-Host ""
    }

    return ,$Items
}

# --------------------------------------------------
# MAIN
# --------------------------------------------------

try {

    if (-not (Test-Path $ProjectDir)) {
        Fail "Project directory not found: $ProjectDir"
    }

    Write-Log "EmbedCo Windows Installer"
    Write-Log "Project: $ProjectDir"

    $Items = @(
        @{
            Key = "arduino-cli"
            Label = "Install Arduino CLI"
            Selected = (-not $SkipArduinoCli)
        },
        @{
            Key = "python-deps"
            Label = "Install Python dependencies"
            Selected = (-not $SkipPythonDeps)
        },
        @{
            Key = "core-update"
            Label = "Update Arduino core index"
            Selected = $false
        },
        @{
            Key = "avr-core"
            Label = "Install Arduino AVR core"
            Selected = $false
        }
    )

    $Interactive = $false

    if (-not $NonInteractive -and
        [Environment]::UserInteractive -and
        [Console]::IsInputRedirected -eq $false -and
        [Console]::IsOutputRedirected -eq $false) {

        $Interactive = $true
    }

    if ($Interactive) {
        $Items = Show-CheckboxMenu $Items
    }
    else {
        Write-Log "Using default installation options."
    }

    $Selected = @{}

    foreach ($Item in $Items) {
        $Selected[$Item.Key] = [bool]$Item.Selected
    }

    $NeedsCLI = $Selected["core-update"] -or
                $Selected["avr-core"]

    if ($Selected["arduino-cli"]) {
        Install-ArduinoCli
    }
    elseif ($NeedsCLI -and -not (Get-ArduinoCliPath)) {
        Fail "Arduino CLI is required for the selected core operations."
    }
    else {
        Write-Log "Skipping Arduino CLI."
    }

    if ($Selected["python-deps"]) {
        Install-PythonDeps
    }
    else {
        Write-Log "Skipping Python dependencies."
    }

    if ($Selected["core-update"]) {
        Update-CoreIndex
    }
    else {
        Write-Log "Skipping core index update."
    }

    if ($Selected["avr-core"]) {
        Install-AvrCore
    }
    else {
        Write-Log "Skipping AVR core."
    }

    Write-Host ""
    Write-Log "Installation completed successfully."

    Write-Host ""
    Write-Host "Start EmbedCo using:" -ForegroundColor Green
    Write-Host "  python server.py"

    Write-Host ""

    if ($Selected["arduino-cli"] -or $NeedsCLI) {
        Write-Warn "Restart your terminal if Arduino CLI is not recognized."
    }

}
catch {

    Write-Host ""
    Write-Host "INSTALLATION FAILED" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red

    exit 1
}
