<#
.SYNOPSIS
    Improves graph density of Serena memories by adding Related sections.

.DESCRIPTION
    Analyzes memory files and adds Related sections based on:
    - Naming patterns (shared prefixes)
    - Topic domains (security, git, ci, etc.)
    - Cross-references in content

.EXAMPLE
    .\scripts\Improve-MemoryGraphDensity.ps1
#>

[CmdletBinding()]
param(
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$memoriesPath = Join-Path $PSScriptRoot '..' '.serena' 'memories'

# Get all memory files
$memoryFiles = Get-ChildItem -Path $memoriesPath -Filter '*.md' -File

# Build memory name lookup
$memoryNames = @{}
foreach ($file in $memoryFiles) {
    $baseName = $file.BaseName
    $memoryNames[$baseName] = $file.FullName
}

Write-Host "Analyzing $($memoryFiles.Count) memory files..."

# Define domain patterns - files with these prefixes are related
$domainPatterns = @{
    'adr-' = 'Architecture Decision Records'
    'agent-workflow-' = 'Agent Workflow'
    'analysis-' = 'Analysis Patterns'
    'architecture-' = 'Architecture'
    'autonomous-' = 'Autonomous Execution'
    'bash-integration-' = 'Bash Integration'
    'ci-infrastructure-' = 'CI Infrastructure'
    'claude-' = 'Claude Code'
    'coderabbit-' = 'CodeRabbit'
    'copilot-' = 'GitHub Copilot'
    'creator-' = 'Skill Creator'
    'design-' = 'Design Patterns'
    'devops-' = 'DevOps'
    'documentation-' = 'Documentation'
    'git-' = 'Git Operations'
    'git-hooks-' = 'Git Hooks'
    'github-' = 'GitHub'
    'github-cli-' = 'GitHub CLI'
    'gh-extensions-' = 'GitHub Extensions'
    'graphql-' = 'GraphQL'
    'implementation-' = 'Implementation'
    'jq-' = 'JQ'
    'labeler-' = 'GitHub Labeler'
    'linting-' = 'Linting'
    'memory-' = 'Memory Management'
    'merge-resolver-' = 'Merge Resolution'
    'orchestration-' = 'Orchestration'
    'parallel-' = 'Parallel Execution'
    'pattern-' = 'Patterns'
    'pester-' = 'Pester Testing'
    'planning-' = 'Planning'
    'powershell-' = 'PowerShell'
    'pr-' = 'Pull Request'
    'pr-comment-' = 'PR Comments'
    'pr-review-' = 'PR Review'
    'protocol-' = 'Session Protocol'
    'qa-' = 'Quality Assurance'
    'quality-' = 'Quality'
    'retrospective-' = 'Retrospective'
    'security-' = 'Security'
    'session-' = 'Session'
    'session-init-' = 'Session Initialization'
    'skills-' = 'Skills Index'
    'testing-' = 'Testing'
    'triage-' = 'Triage'
    'utilities-' = 'Utilities'
    'validation-' = 'Validation'
    'workflow-' = 'Workflow Patterns'
}

$filesUpdated = 0
$relationshipsAdded = 0

foreach ($file in $memoryFiles) {
    $content = Get-Content $file.FullName -Raw -Encoding UTF8

    # Skip empty files
    if ([string]::IsNullOrEmpty($content)) {
        continue
    }

    # Check if file already has a Related section
    $hasRelated = $content -match '^## Related'

    # Find related files based on naming pattern
    $baseName = $file.BaseName
    $relatedFiles = @()

    # Find files in same domain
    foreach ($pattern in $domainPatterns.Keys) {
        if ($baseName -like "$pattern*") {
            # Find other files with same pattern
            $domainFiles = $memoryFiles | Where-Object {
                $_.BaseName -like "$pattern*" -and
                $_.BaseName -ne $baseName
            } | Select-Object -First 5

            foreach ($domainFile in $domainFiles) {
                $relatedFiles += $domainFile.BaseName
            }
            break
        }
    }

    # Find index files for this domain
    $domainName = ($baseName -split '-')[0]
    $indexFile = "${domainName}s-index"
    if ($memoryNames.ContainsKey($indexFile) -and $baseName -ne $indexFile) {
        $relatedFiles += $indexFile
    }

    # If no Related section exists and we found related files, add one
    if (-not $hasRelated -and $relatedFiles.Count -gt 0) {
        # Remove duplicates and limit to top 5
        $relatedFiles = $relatedFiles | Select-Object -Unique | Select-Object -First 5

        # Build Related section
        $relatedSection = "`n## Related`n`n"
        foreach ($relatedFile in $relatedFiles) {
            $relatedSection += "- [$relatedFile]($relatedFile.md)`n"
        }

        # Add to end of file
        $newContent = $content.TrimEnd() + "`n" + $relatedSection

        if (-not $DryRun) {
            Set-Content -Path $file.FullName -Value $newContent -NoNewline -Encoding UTF8
            Write-Host "Added Related section to: $($file.Name)"
        } else {
            Write-Host "[DRY RUN] Would add Related section to: $($file.Name)"
        }

        $filesUpdated++
        $relationshipsAdded += $relatedFiles.Count
    }
}

Write-Host "`n=== Summary ==="
Write-Host "Files updated: $filesUpdated"
Write-Host "Relationships added: $relationshipsAdded"
Write-Host "Current coverage: $((219 + $filesUpdated) / 600 * 100)%"

if ($DryRun) {
    Write-Host "`nThis was a dry run. Use without -DryRun to apply changes."
}
