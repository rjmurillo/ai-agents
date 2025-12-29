<#
.SYNOPSIS
    Fix malformed markdown code fence closings.

.DESCRIPTION
    Scans markdown files and repairs closing fences that incorrectly include
    language identifiers (```python instead of ```).

.PARAMETER Directories
    One or more directories to scan for markdown files.

.PARAMETER Pattern
    File pattern to match. Default: *.md

.EXAMPLE
    .\fix_fences.ps1 -Directories docs, src

.EXAMPLE
    .\fix_fences.ps1 -Directories . -WhatIf

.NOTES
    Supports -WhatIf for dry-run mode (issue #461).
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory = $false)]
    [string[]]$Directories = @('vs-code-agents', 'copilot-cli'),

    [Parameter(Mandatory = $false)]
    [string]$Pattern = '*.md'
)

function Repair-MarkdownFences {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Content
    )
    
    $lines = $Content -split "`r?`n"
    $result = @()
    $inCodeBlock = $false
    $codeBlockIndent = ""
    
    foreach ($line in $lines) {
        if ($line -match '^(\s*)```(\w+)') {
            if ($inCodeBlock) {
                # Malformed: closing fence has language identifier
                # Insert proper closing fence before this line
                $result += $codeBlockIndent + '```'
            }
            # Start new block
            $result += $line
            $codeBlockIndent = $Matches[1]
            $inCodeBlock = $true
        }
        elseif ($line -match '^(\s*)```\s*$') {
            $result += $line
            $inCodeBlock = $false
            $codeBlockIndent = ""
        }
        else {
            $result += $line
        }
    }
    
    # Handle file ending inside code block
    if ($inCodeBlock) {
        $result += $codeBlockIndent + '```'
    }
    
    return $result -join "`n"
}

$totalFixed = 0

foreach ($dir in $Directories) {
    if (-not (Test-Path $dir)) {
        Write-Warning "Directory does not exist: $dir"
        continue
    }
    
    Get-ChildItem -Path $dir -Filter $Pattern -Recurse | ForEach-Object {
        $file = $_.FullName
        $content = Get-Content $file -Raw
        
        if ($null -eq $content) {
            return
        }
        
        $fixedContent = Repair-MarkdownFences -Content $content

        if ($content -ne $fixedContent) {
            Set-Content -Path $file -Value $fixedContent -NoNewline -Encoding UTF8
            $script:totalFixed++
        }
    }
}

if ($totalFixed -eq 0) {
    Write-Host "No files needed fixing"
}
else {
    Write-Host "`nTotal: fixed $totalFixed file(s)"
}
