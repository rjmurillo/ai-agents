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
        - zstd compression tool (automatically installed if missing)

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

function Install-Zstd {
    <#
    .SYNOPSIS
        Installs zstd compression tool if not already available.

    .DESCRIPTION
        Detects the current platform and installs zstd using the appropriate package manager:
        - Windows: winget or manual download from GitHub releases
        - Linux (Debian/Ubuntu): apt-get
        - Linux (RHEL/Fedora): dnf
        - macOS: brew

    .PARAMETER CI
        Enables CI mode with non-interactive behavior.

    .OUTPUTS
        [bool] True if zstd is available after installation attempt.
    #>
    [CmdletBinding()]
    param(
        [Parameter()]
        [switch]$CI
    )

    # Check if zstd is already available
    $zstdCmd = Get-Command zstd -ErrorAction SilentlyContinue
    if ($zstdCmd) {
        Write-Verbose "zstd is already installed at: $($zstdCmd.Source)"
        return $true
    }

    if (-not $CI) {
        Write-Host "zstd not found. Attempting to install..." -ForegroundColor Yellow
    }

    try {
        if ($IsWindows) {
            # Try winget first (modern Windows package manager)
            $wingetCmd = Get-Command winget -ErrorAction SilentlyContinue
            if ($wingetCmd) {
                if (-not $CI) {
                    Write-Host "Installing zstd via winget..." -ForegroundColor Cyan
                }
                winget install --id Facebook.zstd --exact --silent --accept-source-agreements 2>&1 | Out-Null

                # Verify installation
                $zstdCmd = Get-Command zstd -ErrorAction SilentlyContinue
                if ($zstdCmd) {
                    if (-not $CI) {
                        Write-Host "Successfully installed zstd via winget" -ForegroundColor Green
                    }
                    return $true
                }
            }

            # Fallback: Provide manual installation instructions
            $errorMessage = @"
Failed to install zstd automatically on Windows.

Please install manually using one of these methods:
  1. Using winget: winget install Facebook.zstd
  2. Download from: https://github.com/facebook/zstd/releases
     - Download the Windows binary (zstd-v*-win64.zip)
     - Extract zstd.exe to a directory in your PATH

After installation, restart PowerShell and run this script again.
"@
            throw $errorMessage
        }
        elseif ($IsLinux) {
            # Detect Linux distribution
            if (Test-Path "/etc/os-release") {
                $osRelease = Get-Content "/etc/os-release" -Raw

                if ($osRelease -match 'ID_LIKE=.*debian' -or $osRelease -match 'ID=debian' -or $osRelease -match 'ID=ubuntu') {
                    # Debian/Ubuntu
                    if (-not $CI) {
                        Write-Host "Installing zstd via apt-get..." -ForegroundColor Cyan
                    }

                    # Update package list and install zstd
                    sudo apt-get update 2>&1 | Out-Null
                    sudo apt-get install -y zstd 2>&1 | Out-Null

                    # Verify installation
                    $zstdCmd = Get-Command zstd -ErrorAction SilentlyContinue
                    if ($zstdCmd) {
                        if (-not $CI) {
                            Write-Host "Successfully installed zstd via apt-get" -ForegroundColor Green
                        }
                        return $true
                    }
                }
                elseif ($osRelease -match 'ID_LIKE=.*rhel' -or $osRelease -match 'ID_LIKE=.*fedora' -or $osRelease -match 'ID=rhel' -or $osRelease -match 'ID=fedora') {
                    # RHEL/Fedora
                    if (-not $CI) {
                        Write-Host "Installing zstd via dnf..." -ForegroundColor Cyan
                    }

                    sudo dnf install -y zstd 2>&1 | Out-Null

                    # Verify installation
                    $zstdCmd = Get-Command zstd -ErrorAction SilentlyContinue
                    if ($zstdCmd) {
                        if (-not $CI) {
                            Write-Host "Successfully installed zstd via dnf" -ForegroundColor Green
                        }
                        return $true
                    }
                }
            }

            # Fallback: Provide manual installation instructions
            $errorMessage = @"
Failed to install zstd automatically on Linux.

Please install manually using your distribution's package manager:
  - Debian/Ubuntu: sudo apt-get install zstd
  - RHEL/Fedora: sudo dnf install zstd
  - Other: Check your distribution's package repository

After installation, run this script again.
"@
            throw $errorMessage
        }
        elseif ($IsMacOS) {
            # macOS with Homebrew
            $brewCmd = Get-Command brew -ErrorAction SilentlyContinue
            if ($brewCmd) {
                if (-not $CI) {
                    Write-Host "Installing zstd via Homebrew..." -ForegroundColor Cyan
                }

                brew install zstd 2>&1 | Out-Null

                # Verify installation
                $zstdCmd = Get-Command zstd -ErrorAction SilentlyContinue
                if ($zstdCmd) {
                    if (-not $CI) {
                        Write-Host "Successfully installed zstd via Homebrew" -ForegroundColor Green
                    }
                    return $true
                }
            }

            # Fallback: Provide manual installation instructions
            $errorMessage = @"
Failed to install zstd automatically on macOS.

Please install Homebrew and zstd:
  1. Install Homebrew: https://brew.sh
  2. Install zstd: brew install zstd

After installation, run this script again.
"@
            throw $errorMessage
        }
        else {
            throw "Unsupported platform for automatic zstd installation."
        }
    }
    catch {
        Write-Verbose "zstd installation failed: $_"
        return $false
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
            throw "Failed to download CodeQL CLI: $_"
        }

        if (-not $CI) {
            Write-Host "Download complete. Extracting..." -ForegroundColor Cyan
        }

        # Extract tar.zst archive
        # PowerShell 7+ has native tar support, but .zst requires external tool or extraction in steps
        $extractDir = Join-Path $tempDir "extracted"
        New-Item -ItemType Directory -Path $extractDir -Force | Out-Null

        $extractionSucceeded = $false

        # Method 1: Try tar with built-in zstd support (modern GNU tar)
        try {
            $tarVersion = tar --version 2>&1
            if ($LASTEXITCODE -eq 0 -and $tarVersion -match 'zstd') {
                if (-not $CI) {
                    Write-Host "Using tar with native zstd support..." -ForegroundColor Cyan
                }
                tar -xf $archivePath -C $extractDir --zstd 2>&1 | Out-Null
                if ($LASTEXITCODE -eq 0) {
                    $extractionSucceeded = $true
                }
            }
        }
        catch {
            Write-Verbose "tar with zstd support not available: $_"
        }

        # Method 2: Try zstd decompress + tar extract (two-step)
        if (-not $extractionSucceeded) {
            $zstdCmd = Get-Command zstd -ErrorAction SilentlyContinue

            # If zstd is not available, try to install it
            if (-not $zstdCmd) {
                if (-not $CI) {
                    Write-Host "zstd not found. Attempting automatic installation..." -ForegroundColor Yellow
                }

                $zstdInstalled = Install-Zstd -CI:$CI
                if ($zstdInstalled) {
                    $zstdCmd = Get-Command zstd -ErrorAction SilentlyContinue
                }
            }

            if ($zstdCmd) {
                try {
                    if (-not $CI) {
                        Write-Host "Using zstd + tar (two-step extraction)..." -ForegroundColor Cyan
                    }
                    $tarPath = Join-Path $tempDir "codeql-bundle.tar"

                    # Decompress zstd to tar
                    & zstd -d $archivePath -o $tarPath 2>&1 | Out-Null
                    if ($LASTEXITCODE -ne 0) {
                        throw "zstd decompression failed with exit code $LASTEXITCODE"
                    }

                    # Extract tar
                    tar -xf $tarPath -C $extractDir 2>&1 | Out-Null
                    if ($LASTEXITCODE -eq 0) {
                        $extractionSucceeded = $true
                    }
                }
                catch {
                    Write-Verbose "zstd + tar extraction failed: $_"
                }
            }
        }

        # Method 3: Windows - try downloading zip format if available
        if (-not $extractionSucceeded -and $IsWindows) {
            try {
                # Try to download zip version instead (older CodeQL releases had zip)
                $zipUrl = $Url -replace '\.tar\.zst$', '.zip'
                $zipPath = Join-Path $tempDir "codeql-bundle.zip"

                if (-not $CI) {
                    Write-Host "Attempting to download zip format for Windows..." -ForegroundColor Cyan
                }

                $testResponse = Invoke-WebRequest -Uri $zipUrl -Method Head -UseBasicParsing -ErrorAction SilentlyContinue
                if ($testResponse.StatusCode -eq 200) {
                    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing
                    Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force
                    $extractionSucceeded = $true
                }
            }
            catch {
                Write-Verbose "Zip download/extraction failed: $_"
            }
        }

        # Method 4: Provide helpful error message if all extraction methods failed
        if (-not $extractionSucceeded) {
            $errorMessage = @"
Failed to extract CodeQL CLI bundle. No suitable extraction method found.

The CodeQL CLI bundle uses .tar.zst format which requires one of:
  1. GNU tar with zstd support (tar --version should show 'zstd')
  2. Standalone zstd tool

Automatic installation was attempted but failed. Please install manually:
  - Windows: winget install Facebook.zstd, or download from https://github.com/facebook/zstd/releases
  - Linux (Debian/Ubuntu): sudo apt-get install zstd
  - Linux (RHEL/Fedora): sudo dnf install zstd
  - macOS: brew install zstd

After installation, run this script again.
"@
            throw $errorMessage
        }

        # Move extracted files to destination
        $codeqlDir = Join-Path $extractDir "codeql"
        if (-not (Test-Path $codeqlDir)) {
            throw "Extraction succeeded but expected 'codeql' directory not found."
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

        # Exit code 3 for external dependency errors (download, extraction failures)
        # Exit code 1 for logic errors
        $errorMessage = $_.Exception.Message
        if ($errorMessage -match 'download|extract|zstd|tar|codeql directory not found') {
            exit 3
        }
        exit 1
    }
} # End of direct execution check

#endregion
