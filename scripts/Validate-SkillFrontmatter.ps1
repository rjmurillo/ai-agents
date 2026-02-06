<#
.SYNOPSIS
    Validates Claude Code skill YAML frontmatter against schema requirements.

.DESCRIPTION
    Enforces frontmatter constraints for SKILL.md files:
    - YAML syntax (delimiters, indentation)
    - Required fields: name, description
    - Name format: lowercase alphanumeric + hyphens, max 64 chars (regex: ^[a-z0-9-]{1,64}$)
    - Description: non-empty, max 1024 chars, no XML tags
    - Model: valid model identifiers (aliases or dated snapshots)
    - Allowed-tools: valid Claude Code tool names (if present)

    This validation runs on staged .claude/skills/*/SKILL.md files during pre-commit.

.PARAMETER Path
    Path to SKILL.md file or directory containing SKILL.md. Defaults to .claude/skills/.

.PARAMETER CI
    Run in CI mode (stricter output, exit codes).

.PARAMETER StagedOnly
    Only check staged files (for pre-commit hook).

.PARAMETER ChangedFiles
    Array of file paths to check (for CI workflow). When specified, only these files are validated.

.EXAMPLE
    pwsh scripts/Validate-SkillFrontmatter.ps1

.EXAMPLE
    pwsh scripts/Validate-SkillFrontmatter.ps1 -StagedOnly

.EXAMPLE
    pwsh scripts/Validate-SkillFrontmatter.ps1 -CI -ChangedFiles @('.claude/skills/my-skill/SKILL.md')

.NOTES
  EXIT CODES:
  0  - Success: All skill frontmatter is valid
  1  - Error: Frontmatter validation failed (always when -CI flag is set)

  See: ADR-035 Exit Code Standardization
  Related: ADR-040 (Skill Frontmatter Standardization), Issue #4
  Reference: .agents/analysis/claude-code-skill-frontmatter-2026.md
#>
[CmdletBinding()]
param(
    [string]$Path = ".claude/skills",
    [switch]$CI,
    [switch]$StagedOnly,
    [string[]]$ChangedFiles = @()
)

$ErrorActionPreference = 'Stop'
$script:ExitCode = 0
$script:ValidationErrors = @()

# Valid model identifiers (from .agents/analysis/claude-code-skill-frontmatter-2026.md)
$script:ValidModelAliases = @(
    'claude-opus-4-5',
    'claude-sonnet-4-5',
    'claude-haiku-4-5',
    'claude-sonnet-4-0',
    'claude-3-7-sonnet-latest',
    # CLI shortcuts (optional support)
    'opus',
    'sonnet',
    'haiku'
)

# Dated snapshot pattern: claude-{tier}-4-5-YYYYMMDD
$script:DatedSnapshotPattern = '^claude-(opus|sonnet|haiku)-4-5-\d{8}$'

# Known Claude Code tools (partial list - can be expanded)
$script:ValidTools = @(
    'bash',
    'view',
    'edit',
    'create',
    'grep',
    'glob',
    'task',
    'web_search',
    'web_fetch',
    'mcp',
    'playwright-browser',
    'github-mcp-server',
    'deepwiki',
    'serena',
    'forgetful'
)

function Get-SkillFile {
    <#
    .SYNOPSIS
        Gets list of SKILL.md files to validate based on parameters.
    .DESCRIPTION
        This function uses the script-level parameters to determine which files to validate.
    #>
    [System.Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSUseSingularNouns', '', Justification='Function returns multiple files')]
    param()
    
    if ($ChangedFiles.Count -gt 0) {
        # Use explicitly passed files (from CI workflow)
        $skillFiles = $ChangedFiles |
            Where-Object { $_ -match '\.claude/skills/.*/SKILL\.md$' }

        if (-not $skillFiles) {
            Write-Host "No SKILL.md files in changed files list. Skipping frontmatter validation." -ForegroundColor Gray
            return @()
        }

        # Filter to existing files only (deleted files don't need validation)
        $filesToCheck = $skillFiles | ForEach-Object { 
            if (Test-Path $_) { 
                Get-Item $_ -ErrorAction SilentlyContinue 
            }
        } | Where-Object { $_ -ne $null }
    }
    elseif ($StagedOnly) {
        # Get staged SKILL.md files from git
        $stagedFiles = git diff --cached --name-only --diff-filter=ACMR 2>$null |
            Where-Object { $_ -match '\.claude/skills/.*/SKILL\.md$' }

        if (-not $stagedFiles) {
            Write-Host "No SKILL.md files staged. Skipping frontmatter validation." -ForegroundColor Gray
            return @()
        }

        $filesToCheck = $stagedFiles | ForEach-Object { 
            if (Test-Path $_) { 
                Get-Item $_ -ErrorAction SilentlyContinue 
            }
        } | Where-Object { $_ -ne $null }
    }
    else {
        # Check all SKILL.md files
        if (-not (Test-Path $Path)) {
            Write-Host "Path not found: $Path. Skipping frontmatter validation." -ForegroundColor Gray
            return @()
        }

        # If Path is a file, check just that file
        if ((Get-Item $Path).PSIsContainer -eq $false) {
            if ($Path -match 'SKILL\.md$') {
                $filesToCheck = @(Get-Item $Path)
            }
            else {
                Write-Host "Path is not a SKILL.md file: $Path" -ForegroundColor Gray
                return @()
            }
        }
        else {
            # Find all SKILL.md files recursively
            $filesToCheck = Get-ChildItem -Path $Path -Filter "SKILL.md" -Recurse -ErrorAction SilentlyContinue
        }
    }

    return $filesToCheck
}

function Test-YamlFrontmatter {
    <#
    .SYNOPSIS
        Validates YAML frontmatter syntax and structure.
    
    .PARAMETER Content
        Full content of the SKILL.md file.
    
    .RETURNS
        Hashtable with: IsValid (bool), Frontmatter (hashtable), Errors (string[])
    #>
    param(
        [string]$Content
    )

    $result = @{
        IsValid = $true
        Frontmatter = @{}
        Errors = @()
    }

    # Check if content starts with ---
    if (-not $Content.StartsWith('---')) {
        $result.IsValid = $false
        $result.Errors += "Frontmatter must start with '---' on line 1"
        return $result
    }

    # Extract frontmatter (between first and second ---)
    $lines = $Content -split "`n"
    $frontmatterEnd = -1
    
    for ($i = 1; $i -lt $lines.Count; $i++) {
        if ($lines[$i].Trim() -eq '---') {
            $frontmatterEnd = $i
            break
        }
    }

    if ($frontmatterEnd -eq -1) {
        $result.IsValid = $false
        $result.Errors += "Frontmatter must end with '---'"
        return $result
    }

    # Get frontmatter content (between delimiters)
    $frontmatterContent = ($lines[1..($frontmatterEnd - 1)] -join "`n")

    # Check for tab characters (spaces only for indentation)
    if ($frontmatterContent -match "`t") {
        $result.IsValid = $false
        $result.Errors += "Frontmatter must use spaces for indentation (tabs not allowed)"
    }

    # Parse YAML using simple key-value parsing
    # LIMITATIONS: This parser is simplified and does NOT support:
    #   - Quoted strings with embedded colons or special characters
    #   - Complex nested structures beyond simple arrays
    #   - YAML anchors, aliases, or advanced features
    #   - Precise indentation-based structure parsing
    # It is designed for simple skill frontmatter with key-value pairs and basic arrays.
    # For complex YAML, consider using a dedicated YAML parsing library.
    try {
        $frontmatter = @{}
        $currentKey = $null
        $currentValue = ""
        $inMultilineValue = $false

        foreach ($line in ($frontmatterContent -split "`n")) {
            # Skip empty lines
            if ([string]::IsNullOrWhiteSpace($line)) { continue }

            # Check if this is a key-value line (contains ':')
            if ($line -match '^([a-zA-Z0-9_-]+):\s*(.*)$') {
                # Save previous key-value if exists
                if ($currentKey) {
                    $frontmatter[$currentKey] = $currentValue.Trim()
                }

                $currentKey = $Matches[1]
                $currentValue = $Matches[2]

                # Check for multiline indicator (>)
                if ($currentValue -eq '>' -or $currentValue -eq '|') {
                    $inMultilineValue = $true
                    $currentValue = ""
                }
                else {
                    $inMultilineValue = $false
                }
            }
            elseif ($inMultilineValue) {
                # Continuation of multiline value
                $trimmedLine = $line.TrimStart()
                if ($currentValue) {
                    $currentValue += " " + $trimmedLine
                }
                else {
                    $currentValue = $trimmedLine
                }
            }
            elseif ($line.TrimStart().StartsWith('-')) {
                # Array value (for fields like allowed-tools)
                $arrayValue = $line.TrimStart().Substring(1).Trim()
                if ($currentValue) {
                    $currentValue += "," + $arrayValue
                }
                else {
                    $currentValue = $arrayValue
                }
            }
        }

        # Save last key-value
        if ($currentKey) {
            $frontmatter[$currentKey] = $currentValue.Trim()
        }

        $result.Frontmatter = $frontmatter
    }
    catch {
        $result.IsValid = $false
        $result.Errors += "Failed to parse YAML frontmatter: $($_.Exception.Message)"
    }

    return $result
}

function Test-NameField {
    <#
    .SYNOPSIS
        Validates the 'name' field in frontmatter.
    
    .PARAMETER Name
        Value of the name field.
    
    .RETURNS
        Array of error messages (empty if valid).
    #>
    param([string]$Name)

    $errors = @()

    if ([string]::IsNullOrWhiteSpace($Name)) {
        $errors += "Missing required field: 'name'"
        return $errors
    }

    # Check regex: ^[a-z0-9-]{1,64}$ (case-sensitive)
    if ($Name -cnotmatch '^[a-z0-9-]{1,64}$') {
        $reasonParts = @()
        
        if ($Name -cmatch '[A-Z]') {
            $reasonParts += "contains uppercase letters"
        }
        if ($Name -cmatch '[^a-z0-9-]') {
            $reasonParts += "contains invalid characters (only a-z, 0-9, hyphen allowed)"
        }
        if ($Name.Length -gt 64) {
            $reasonParts += "exceeds 64 characters (found $($Name.Length))"
        }
        if ($Name.Length -eq 0) {
            $reasonParts += "is empty"
        }

        $reason = if ($reasonParts.Count -gt 0) { " ($($reasonParts -join ', '))" } else { "" }
        $errors += "Invalid name format: '$Name'$reason (must match ^[a-z0-9-]{1,64}$)"
    }

    return $errors
}

function Test-DescriptionField {
    <#
    .SYNOPSIS
        Validates the 'description' field in frontmatter.
    
    .PARAMETER Description
        Value of the description field.
    
    .RETURNS
        Array of error messages (empty if valid).
    #>
    param([string]$Description)

    $errors = @()

    if ([string]::IsNullOrWhiteSpace($Description)) {
        $errors += "Missing required field: 'description'"
        return $errors
    }

    # Check max 1024 characters
    if ($Description.Length -gt 1024) {
        $errors += "Description exceeds 1024 characters (found $($Description.Length))"
    }

    # Check for XML tags
    if ($Description -match '<[^>]+>') {
        $errors += "Description contains XML tags (not allowed)"
    }

    return $errors
}

function Test-ModelField {
    <#
    .SYNOPSIS
        Validates the 'model' field in frontmatter (if present).
    
    .PARAMETER Model
        Value of the model field.
    
    .RETURNS
        Array of error messages (empty if valid).
    #>
    param([string]$Model)

    $errors = @()

    # Model is optional, but if present must be valid
    if ([string]::IsNullOrWhiteSpace($Model)) {
        return $errors
    }

    # Check if it's a valid alias
    if ($script:ValidModelAliases -contains $Model) {
        return $errors
    }

    # Check if it's a dated snapshot
    if ($Model -match $script:DatedSnapshotPattern) {
        return $errors
    }

    # Invalid model identifier
    $errors += "Invalid model identifier: '$Model' (use aliases like 'claude-sonnet-4-5' or dated snapshots like 'claude-sonnet-4-5-20250929')"

    return $errors
}

function Test-AllowedToolsField {
    <#
    .SYNOPSIS
        Validates the 'allowed-tools' field in frontmatter (if present).
    
    .PARAMETER AllowedTools
        Value of the allowed-tools field (comma-separated or array).
    
    .RETURNS
        Array of error messages (empty if valid).
    #>
    param([string]$AllowedTools)

    $errors = @()

    # allowed-tools is optional
    if ([string]::IsNullOrWhiteSpace($AllowedTools)) {
        return $errors
    }

    # Parse tools (handle both comma-separated string and array format)
    $tools = $AllowedTools -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ }

    # Check each tool
    $invalidTools = @()
    foreach ($tool in $tools) {
        # Remove any YAML array indicators
        $cleanTool = $tool -replace '^\s*-\s*', ''
        
        # Allow wildcards
        if ($cleanTool -match '\*') {
            continue
        }

        # Check if tool is in valid list
        if ($script:ValidTools -notcontains $cleanTool) {
            $invalidTools += $cleanTool
        }
    }

    if ($invalidTools.Count -gt 0) {
        $errors += "Unknown tools in allowed-tools: $($invalidTools -join ', ')"
    }

    return $errors
}

function Test-SkillFrontmatter {
    <#
    .SYNOPSIS
        Validates a single SKILL.md file.
    
    .PARAMETER File
        FileInfo object for the SKILL.md file.
    
    .RETURNS
        Boolean indicating if validation passed.
    #>
    param([System.IO.FileInfo]$File)

    $filePath = $File.FullName
    $relativePath = $filePath.Replace((Get-Location).Path, '').TrimStart('\', '/')

    Write-Host "  Checking: $relativePath" -ForegroundColor Cyan

    # Read file content
    $content = Get-Content $filePath -Raw -ErrorAction SilentlyContinue
    if (-not $content) {
        Write-Host "    [FAIL] File is empty or unreadable" -ForegroundColor Red
        $script:ValidationErrors += @{
            File = $relativePath
            Errors = @("File is empty or unreadable")
        }
        return $false
    }

    # Validate YAML frontmatter structure
    $yamlResult = Test-YamlFrontmatter -Content $content
    
    $allValidationErrors = @()
    $allValidationErrors += $yamlResult.Errors

    if ($yamlResult.IsValid -and $yamlResult.Frontmatter.Count -gt 0) {
        # Validate required fields
        $allValidationErrors += Test-NameField -Name $yamlResult.Frontmatter['name']
        $allValidationErrors += Test-DescriptionField -Description $yamlResult.Frontmatter['description']

        # Validate optional fields if present
        if ($yamlResult.Frontmatter.ContainsKey('model')) {
            $allValidationErrors += Test-ModelField -Model $yamlResult.Frontmatter['model']
        }

        if ($yamlResult.Frontmatter.ContainsKey('allowed-tools')) {
            $allValidationErrors += Test-AllowedToolsField -AllowedTools $yamlResult.Frontmatter['allowed-tools']
        }
    }

    # Report results
    if ($allValidationErrors.Count -eq 0) {
        Write-Host "    [PASS] Frontmatter is valid" -ForegroundColor Green
        return $true
    }
    else {
        Write-Host "    [FAIL] Frontmatter validation failed:" -ForegroundColor Red
        foreach ($validationError in $allValidationErrors) {
            Write-Host "      - $validationError" -ForegroundColor Red
        }
        
        $script:ValidationErrors += @{
            File = $relativePath
            Errors = $allValidationErrors
        }
        return $false
    }
}

# Main execution
Write-Host "Validating skill frontmatter..." -ForegroundColor Cyan

$filesToCheck = Get-SkillFile

if (-not $filesToCheck -or $filesToCheck.Count -eq 0) {
    Write-Host "No SKILL.md files found to validate." -ForegroundColor Gray
    exit 0
}

Write-Host "Found $($filesToCheck.Count) SKILL.md file(s) to validate." -ForegroundColor Cyan
Write-Host ""

$passCount = 0
$failCount = 0

foreach ($file in $filesToCheck) {
    if (Test-SkillFrontmatter -File $file) {
        $passCount++
    }
    else {
        $failCount++
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Validation Summary" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Total:  $($filesToCheck.Count)" -ForegroundColor White
Write-Host "  Passed: $passCount" -ForegroundColor Green
Write-Host "  Failed: $failCount" -ForegroundColor $(if ($failCount -eq 0) { 'Green' } else { 'Red' })
Write-Host ""

if ($failCount -gt 0) {
    Write-Host "Fix SKILL.md frontmatter and retry commit." -ForegroundColor Red
    Write-Host "See: .agents/analysis/claude-code-skill-frontmatter-2026.md" -ForegroundColor Yellow
    
    if ($CI) {
        exit 1
    }
    else {
        Write-Host ""
        Write-Host "Validation failed, but not running in CI mode. Continuing..." -ForegroundColor Yellow
    }
}
else {
    Write-Host "All skill frontmatter validated successfully!" -ForegroundColor Green
}

exit 0
