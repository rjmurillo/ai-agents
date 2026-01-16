<#
.SYNOPSIS
    Downloads and installs the CodeQL CLI for static analysis.

.DESCRIPTION
    This script downloads the appropriate CodeQL CLI bundle for the current platform
    (Windows, Linux, or macOS) and architecture (x64 or ARM64), extracts it to the
    specified installation path, and optionally adds it to the PATH environment variable.

    The script follows the repository's PowerShell-only convention (ADR-005) and uses
    standardized exit codes (ADR-035).

.PARAMETER Version
    The CodeQL CLI version to install. Defaults to "v2.23.9".
    Must match a valid release tag from github/codeql-action/releases.

.PARAMETER InstallPath
    The directory where CodeQL CLI will be installed. Defaults to ".codeql/cli".
    The script will create this directory if it doesn't exist.

.PARAMETER Force
    If specified, overwrites an existing CodeQL installation at the target path.

.PARAMETER AddToPath
    If specified, adds the CodeQL CLI to the PATH environment variable.
    Updates both session PATH and persistent PATH (user profile scripts on Linux/macOS,
    registry on Windows).

.PARAMETER CI
    Enables CI mode with non-interactive behavior. Suppresses progress output and
    uses appropriate exit codes for automation.

.EXAMPLE
    .\Install-CodeQL.ps1
    Installs CodeQL CLI v2.23.9 to .codeql/cli

.EXAMPLE
    .\Install-CodeQL.ps1 -Version "v2.23.0" -InstallPath "C:\Tools\codeql" -AddToPath
    Installs CodeQL CLI v2.23.0 to C:\Tools\codeql and adds to PATH

.EXAMPLE
    .\Install-CodeQL.ps1 -Force -CI
    Reinstalls CodeQL CLI (overwriting existing) in CI mode

.NOTES
    Exit Codes (per ADR-035):
        0 = Success
        1 = Logic error (invalid parameters, installation check failed)
        2 = Configuration error (invalid version, unsupported platform)
        3 = External dependency error (download failed, extraction failed)

    Platform Support:
        - Windows (x64, ARM64)
        - Linux (x64, ARM64)
        - macOS (x64, ARM64)

    Requirements:
        - PowerShell 7.0 or later
        - Internet connection for initial download
        - Write permissions to installation directory

.LINK
    https://github.com/github/codeql-action/releases
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$Version = "v2.23.9",

    [Parameter()]
    [string]$InstallPath = ".codeql/cli",

    [Parameter()]
    [switch]$Force,

    [Parameter()]
    [switch]$AddToPath,

    [Parameter()]
    [switch]$CI
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

#region Helper Functions

function Get-CodeQLDownloadUrl {
    <#
    .SYNOPSIS
        Constructs the download URL for the CodeQL CLI bundle based on platform and architecture.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Version
    )

    # Detect platform
    $platform = if ($IsWindows) {
        "win64"
    }
    elseif ($IsLinux) {
        "linux64"
    }
    elseif ($IsMacOS) {
        "osx64"
    }
    else {
        throw "Unsupported platform. CodeQL CLI supports Windows, Linux, and macOS only."
    }

    # Detect architecture (currently CodeQL uses 64-bit nomenclature for both x64 and ARM64)
    $arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
    if ($arch -notin @('X64', 'Arm64')) {
        Write-Warning "Detected architecture: $arch. CodeQL CLI bundle naming may not match. Attempting with standard 64-bit bundle."
    }

    # Construct URL
    $baseUrl = "https://github.com/github/codeql-action/releases/download"
    $url = "$baseUrl/$Version/codeql-bundle-$platform.tar.zst"

    return $url
}

function Test-CodeQLInstalled {
    <#
    .SYNOPSIS
        Checks if CodeQL CLI is already installed at the specified path.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    $exeName = if ($IsWindows) { "codeql.exe" } else { "codeql" }
    $codeqlPath = Join-Path $Path $exeName

    if (Test-Path $codeqlPath) {
        try {
            $versionOutput = & $codeqlPath version 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Verbose "Found CodeQL CLI at $codeqlPath"
                Write-Verbose "Version: $versionOutput"
                return $true
            }
        }
        catch {
            Write-Verbose "CodeQL executable found but failed to run: $_"
        }
    }

    return $false
}

function Install-CodeQLCLI {
    <#
    .SYNOPSIS
        Downloads and extracts the CodeQL CLI bundle.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Url,

        [Parameter(Mandatory)]
        [string]$DestinationPath
    )

    # Create temp directory for download
    $tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "codeql-install-$(Get-Random)"
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

    try {
        $archivePath = Join-Path $tempDir "codeql-bundle.tar.zst"

        # Download bundle
        if (-not $CI) {
            Write-Host "Downloading CodeQL CLI from $Url..." -ForegroundColor Cyan
        }

        try {
            $ProgressPreference = if ($CI) { 'SilentlyContinue' } else { 'Continue' }
            Invoke-WebRequest -Uri $Url -OutFile $archivePath -UseBasicParsing
        }
        catch {
            Write-Error "Failed to download CodeQL CLI: $_"
            exit 3
        }

        if (-not $CI) {
            Write-Host "Download complete. Extracting..." -ForegroundColor Cyan
        }

        # Extract tar.zst archive
        # PowerShell 7+ has native tar support, but .zst requires external tool or extraction in steps
        try {
            # Check if tar with zstd support is available
            $tarVersion = tar --version 2>&1
            if ($LASTEXITCODE -eq 0 -and $tarVersion -match 'zstd') {
                # Modern tar with zstd support
                $extractDir = Join-Path $tempDir "extracted"
                New-Item -ItemType Directory -Path $extractDir -Force | Out-Null
                tar -xf $archivePath -C $extractDir --zstd 2>&1 | Out-Null
                if ($LASTEXITCODE -ne 0) {
                    throw "tar extraction failed with exit code $LASTEXITCODE"
                }
            }
            else {
                # Fallback: decompress zstd first, then extract tar
                throw "tar with zstd support not found. Please install zstd or use a system with modern tar."
            }
        }
        catch {
            Write-Error "Failed to extract CodeQL CLI bundle: $_"
            Write-Error "Ensure 'tar' with zstd support is available on your system."
            exit 3
        }

        # Move extracted files to destination
        $codeqlDir = Join-Path $extractDir "codeql"
        if (-not (Test-Path $codeqlDir)) {
            Write-Error "Extraction succeeded but expected 'codeql' directory not found."
            exit 3
        }

        # Create parent directory if needed
        $parentDir = Split-Path $DestinationPath -Parent
        if ($parentDir -and -not (Test-Path $parentDir)) {
            New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
        }

        # Move to final destination
        if (Test-Path $DestinationPath) {
            Remove-Item -Path $DestinationPath -Recurse -Force
        }
        Move-Item -Path $codeqlDir -Destination $DestinationPath -Force

        if (-not $CI) {
            Write-Host "CodeQL CLI installed successfully to $DestinationPath" -ForegroundColor Green
        }
    }
    finally {
        # Cleanup temp files
        if (Test-Path $tempDir) {
            Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

function Add-CodeQLToPath {
    <#
    .SYNOPSIS
        Adds CodeQL CLI to PATH environment variable (session and persistent).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    # Resolve to absolute path
    $absolutePath = Resolve-Path $Path -ErrorAction SilentlyContinue
    if (-not $absolutePath) {
        $absolutePath = (New-Item -ItemType Directory -Path $Path -Force).FullName
    }
    else {
        $absolutePath = $absolutePath.Path
    }

    # Check if already in PATH
    $currentPath = $env:PATH
    if ($currentPath -split [IO.Path]::PathSeparator | Where-Object { $_ -eq $absolutePath }) {
        Write-Verbose "CodeQL CLI path already in PATH"
        return
    }

    # Add to session PATH
    $separator = if ($IsWindows) { ';' } else { ':' }
    $env:PATH = "$absolutePath$separator$env:PATH"

    if (-not $CI) {
        Write-Host "Added CodeQL CLI to session PATH" -ForegroundColor Green
    }

    # Add to persistent PATH
    try {
        if ($IsWindows) {
            # Windows: Update user environment variable via registry
            $regPath = 'HKCU:\Environment'
            $currentUserPath = (Get-ItemProperty -Path $regPath -Name PATH).PATH
            if ($currentUserPath -notlike "*$absolutePath*") {
                $newPath = "$absolutePath;$currentUserPath"
                Set-ItemProperty -Path $regPath -Name PATH -Value $newPath
                if (-not $CI) {
                    Write-Host "Added CodeQL CLI to persistent PATH (user environment)" -ForegroundColor Green
                    Write-Host "Note: Restart terminal or applications to pick up the PATH change" -ForegroundColor Yellow
                }
            }
        }
        else {
            # Linux/macOS: Append to shell profile scripts
            $profileScripts = @()
            $homeDir = [Environment]::GetFolderPath('UserProfile')

            if ($env:SHELL -like '*/bash*') {
                $profileScripts += Join-Path $homeDir '.bashrc'
            }
            if ($env:SHELL -like '*/zsh*') {
                $profileScripts += Join-Path $homeDir '.zshrc'
            }
            # Always add to .profile as fallback
            $profileScripts += Join-Path $homeDir '.profile'

            $exportLine = "export PATH=`"$absolutePath`$separator`$PATH`""

            foreach ($profileScript in $profileScripts | Select-Object -Unique) {
                if (Test-Path $profileScript) {
                    $content = Get-Content $profileScript -Raw
                    if ($content -notmatch [regex]::Escape($absolutePath)) {
                        Add-Content -Path $profileScript -Value "`n# Added by CodeQL installer`n$exportLine"
                        if (-not $CI) {
                            Write-Host "Added CodeQL CLI to $profileScript" -ForegroundColor Green
                        }
                    }
                }
                else {
                    # Create profile if it doesn't exist
                    "# Added by CodeQL installer`n$exportLine" | Out-File -FilePath $profileScript -Encoding utf8
                    if (-not $CI) {
                        Write-Host "Created $profileScript with CodeQL CLI path" -ForegroundColor Green
                    }
                }
            }

            if (-not $CI) {
                Write-Host "Note: Restart terminal to pick up the PATH change" -ForegroundColor Yellow
            }
        }
    }
    catch {
        Write-Warning "Failed to add CodeQL CLI to persistent PATH: $_"
        Write-Warning "You can manually add it: $absolutePath"
    }
}

#endregion

#region Main Script

# Only execute main logic if script is run directly, not dot-sourced for testing
if ($MyInvocation.InvocationName -ne '.') {
    try {
        # Resolve installation path to absolute
        if (-not [System.IO.Path]::IsPathRooted($InstallPath)) {
            $InstallPath = Join-Path $PWD $InstallPath
        }

        # Check if already installed
        if (Test-CodeQLInstalled -Path $InstallPath) {
            if ($Force) {
                if (-not $CI) {
                    Write-Host "CodeQL CLI already installed. Reinstalling due to -Force flag." -ForegroundColor Yellow
                }
            }
            else {
                if (-not $CI) {
                    Write-Host "CodeQL CLI is already installed at $InstallPath" -ForegroundColor Green
                    Write-Host "Use -Force to reinstall" -ForegroundColor Yellow
                }
                exit 0
            }
        }

        # Get download URL
        $downloadUrl = Get-CodeQLDownloadUrl -Version $Version

        # Install CodeQL CLI
        Install-CodeQLCLI -Url $downloadUrl -DestinationPath $InstallPath

        # Add to PATH if requested
        if ($AddToPath) {
            Add-CodeQLToPath -Path $InstallPath
        }

        # Verify installation
        if (-not (Test-CodeQLInstalled -Path $InstallPath)) {
            Write-Error "Installation completed but CodeQL CLI verification failed."
            exit 1
        }

        if (-not $CI) {
            Write-Host "`nCodeQL CLI installation complete!" -ForegroundColor Green
            Write-Host "Location: $InstallPath" -ForegroundColor Cyan
            if ($AddToPath) {
                Write-Host "Added to PATH: Yes (restart terminal to use)" -ForegroundColor Cyan
            }
            else {
                Write-Host "Added to PATH: No (use -AddToPath to enable)" -ForegroundColor Cyan
            }
        }

        exit 0
    }
    catch {
        Write-Error "CodeQL CLI installation failed: $_"
        Write-Error $_.ScriptStackTrace
        exit 1
    }
} # End of direct execution check

#endregion
