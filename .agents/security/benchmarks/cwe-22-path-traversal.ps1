<#
.SYNOPSIS
Benchmark test cases for CWE-22 Path Traversal vulnerabilities.

.DESCRIPTION
Contains 5 test cases demonstrating path traversal patterns that security agent
should detect. Based on real vulnerabilities from PR #752.

TEST CASE STRUCTURE:
- VULNERABLE: Marks exploitable code pattern
- EXPECTED: Security agent should flag as CRITICAL
- SOURCE: Real-world vulnerability reference
#>

# ==============================================================================
# TEST CASE 1: StartsWith without GetFullPath normalization (PR #752 actual)
# ==============================================================================

# VULNERABLE: CWE-22 - Path traversal via .. sequences, StartsWith check ineffective
# EXPECTED: CRITICAL - Path traversal allows writing outside allowed directory
# SOURCE: PR #752 Export-ClaudeMemMemories.ps1:105

function Export-Memory-Vulnerable1 {
    param(
        [string]$OutputFile,
        [string]$MemoriesDir = ".claude-mem/memories"
    )

    # UNSAFE: StartsWith does not normalize .. sequences before comparison
    if (-not $OutputFile.StartsWith($MemoriesDir)) {
        Write-Warning "Output file should be in $MemoriesDir"
        # WARNING ONLY - does not block execution
    }

    # Attack: $OutputFile = "..\..\..\..\etc\passwd"
    # Result: StartsWith check passes, file written outside $MemoriesDir
    Set-Content -Path $OutputFile -Value "data"
}

# ==============================================================================
# TEST CASE 2: Join-Path with unvalidated user input
# ==============================================================================

# VULNERABLE: CWE-22 - Path traversal via absolute path in Join-Path
# EXPECTED: CRITICAL - User can specify absolute paths bypassing containment
# SOURCE: Common pattern in memory management scripts

function Save-UserFile-Vulnerable2 {
    param(
        [string]$FileName,
        [string]$BaseDir = "uploads"
    )

    # UNSAFE: Join-Path accepts absolute paths, bypassing BaseDir
    $fullPath = Join-Path $BaseDir $FileName

    # Attack: $FileName = "C:\Windows\System32\malware.exe"
    # Result: Join-Path returns "C:\Windows\System32\malware.exe", ignoring $BaseDir
    Set-Content -Path $fullPath -Value "malicious content"
}

# ==============================================================================
# TEST CASE 3: Relative path without validation
# ==============================================================================

# VULNERABLE: CWE-22 - No path validation, .. sequences allowed
# EXPECTED: CRITICAL - Arbitrary file read via .. sequences
# SOURCE: File processing scripts without path checks

function Read-ConfigFile-Vulnerable3 {
    param(
        [string]$ConfigName
    )

    $configDir = "config"

    # UNSAFE: No validation on $ConfigName, allows .. sequences
    $configPath = Join-Path $configDir $ConfigName

    # Attack: $ConfigName = "..\..\..\etc\passwd"
    # Result: Reads arbitrary system files
    return Get-Content -Path $configPath -Raw
}

# ==============================================================================
# TEST CASE 4: String concatenation for path building
# ==============================================================================

# VULNERABLE: CWE-22 - Path concatenation without normalization
# EXPECTED: CRITICAL - Path traversal via string manipulation
# SOURCE: Legacy scripts using string concat instead of Join-Path

function Delete-TempFile-Vulnerable4 {
    param(
        [string]$TempFileName
    )

    $tempDir = "C:\Temp"

    # UNSAFE: String concatenation doesn't validate or normalize paths
    $fullPath = "$tempDir\$TempFileName"

    # Attack: $TempFileName = "..\..\..\Windows\System32\critical.dll"
    # Result: Deletes files outside temp directory
    Remove-Item -Path $fullPath -Force
}

# ==============================================================================
# TEST CASE 5: Symlink without ReparsePoint check
# ==============================================================================

# VULNERABLE: CWE-22 - TOCTOU race condition with symlinks
# EXPECTED: HIGH - Symlink can be created between validation and use
# SOURCE: PR #752 Import-ClaudeMemMemories.ps1 (correctly flagged by agent)

function Process-Files-Vulnerable5 {
    param(
        [string]$InputDir
    )

    # MISSING: No check for ReparsePoint attribute (symlinks)
    $files = Get-ChildItem -Path $InputDir -File

    foreach ($file in $files) {
        # UNSAFE: Symlink could point outside $InputDir
        # TOCTOU: Symlink created after Get-ChildItem, before Get-Content
        $content = Get-Content -Path $file.FullName
        Write-Host "Processing: $($file.Name)"
    }
}

# CORRECT IMPLEMENTATION: How to fix each vulnerability

function Export-Memory-Secure1 {
    param(
        [string]$OutputFile,
        [string]$MemoriesDir = ".claude-mem/memories"
    )

    # SECURE: Normalize paths before comparison
    $normalizedOutput = [System.IO.Path]::GetFullPath($OutputFile)
    $normalizedDir = [System.IO.Path]::GetFullPath($MemoriesDir)

    if (-not $normalizedOutput.StartsWith($normalizedDir, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Path traversal attempt detected. Output file must be inside '$MemoriesDir' directory."
    }

    Set-Content -Path $normalizedOutput -Value "data"
}

function Save-UserFile-Secure2 {
    param(
        [string]$FileName,
        [string]$BaseDir = "uploads"
    )

    # SECURE: Validate FileName does not contain path separators or .. sequences
    if ($FileName -match '[\\/]|\.\.') {
        throw "Invalid filename. Path separators and .. sequences not allowed."
    }

    $fullPath = Join-Path $BaseDir $FileName
    $normalizedPath = [System.IO.Path]::GetFullPath($fullPath)
    $normalizedBase = [System.IO.Path]::GetFullPath($BaseDir)

    # Double-check after normalization
    if (-not $normalizedPath.StartsWith($normalizedBase)) {
        throw "Path traversal attempt detected."
    }

    Set-Content -Path $normalizedPath -Value "content"
}

function Process-Files-Secure5 {
    param(
        [string]$InputDir
    )

    $files = Get-ChildItem -Path $InputDir -File

    foreach ($file in $files) {
        # SECURE: Check for symlinks and skip them
        if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            Write-Warning "Skipping symlink: $($file.Name)"
            continue
        }

        $content = Get-Content -Path $file.FullName
        Write-Host "Processing: $($file.Name)"
    }
}

<#
SUMMARY OF EXPECTED FINDINGS:

CRITICAL-001: Export-Memory-Vulnerable1 - StartsWith without GetFullPath
CRITICAL-002: Save-UserFile-Vulnerable2 - Absolute path bypass in Join-Path
CRITICAL-003: Read-ConfigFile-Vulnerable3 - No path validation
CRITICAL-004: Delete-TempFile-Vulnerable4 - String concatenation path building
HIGH-001: Process-Files-Vulnerable5 - TOCTOU symlink race condition

Total: 4 CRITICAL, 1 HIGH
Pass Rate Target: 5/5 detected = 100%
#>
