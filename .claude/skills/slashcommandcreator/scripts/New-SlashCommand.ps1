#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Create new slash command with frontmatter template.

.DESCRIPTION
    Automates slash command file creation with proper frontmatter structure.
    Generates a template file that passes initial validation.

.PARAMETER Name
    Command name (e.g., "security-audit"). Required.

.PARAMETER Namespace
    Optional namespace (e.g., "git", "memory"). Creates subdirectory if needed.

.EXAMPLE
    .\New-SlashCommand.ps1 -Name "security-audit"
    Creates .claude/commands/security-audit.md

.EXAMPLE
    .\New-SlashCommand.ps1 -Name "status" -Namespace "git"
    Creates .claude/commands/git/status.md
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$Name,

    [Parameter(Mandatory = $false)]
    [string]$Namespace
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Validate input to prevent path traversal (CWE-22)
# WHY: User-controlled $Name and $Namespace are used in file paths
# SECURITY: Reject any characters that could enable directory traversal
if ($Name -notmatch '^[a-zA-Z0-9_-]+$') {
    Write-Error "Name must contain only alphanumeric characters, hyphens, or underscores"
    exit 1
}
if ($Namespace -and $Namespace -notmatch '^[a-zA-Z0-9_-]+$') {
    Write-Error "Namespace must contain only alphanumeric characters, hyphens, or underscores"
    exit 1
}

# Determine file path
$baseDir = ".claude/commands"
$filePath = if ($Namespace) {
    "$baseDir/$Namespace/$Name.md"
} else {
    "$baseDir/$Name.md"
}

# Check if file exists
if (Test-Path $filePath) {
    Write-Error "File already exists: $filePath"
    exit 1
}

# Ensure directory exists
$directory = Split-Path -Path $filePath -Parent
if (-not (Test-Path $directory)) {
    try {
        New-Item -ItemType Directory -Path $directory -Force -ErrorAction Stop | Out-Null
        Write-Verbose "Created directory: $directory"
    }
    catch {
        Write-Error "Failed to create commands directory '$directory': $_`nCheck permissions, disk space, and path validity"
        exit 1
    }
}

# Generate frontmatter template
# WHY: Empty allowed-tools array forces explicit security review during Phase 3.
# Alternative considered: Omit field entirely. But explicit empty signals
# "reviewed and no tools needed" vs "forgot to add".
$argumentsLiteral = '$ARGUMENTS'
$template = @"
---
description: Use when Claude needs to [FILL IN: when to use this command]
argument-hint: <arg>
allowed-tools: []
---

# $Name Command

[FILL IN: Detailed prompt instructions]

## Arguments

- ``$argumentsLiteral``: [FILL IN: what argument is expected]

## Example

``````text
/$Name [example argument]
``````
"@

try {
    $template | Out-File -FilePath $filePath -Encoding utf8 -ErrorAction Stop
    if (-not (Test-Path $filePath)) {
        throw "File write succeeded but file does not exist"
    }
}
catch {
    Write-Error "Failed to write command file '$filePath': $_`nCheck disk space, file locks, and filesystem health"
    exit 1
}

Write-Host "[PASS] Created: $filePath" -ForegroundColor Green
Write-Host "`nNext steps:" -ForegroundColor Cyan
Write-Host "  1. Edit frontmatter (description, argument-hint, allowed-tools)"
Write-Host "  2. Write prompt body"
Write-Host "  3. Run: pwsh .claude/skills/slashcommandcreator/scripts/Validate-SlashCommand.ps1 -Path $filePath"
Write-Host "  4. Test: /$Name [arguments]"
