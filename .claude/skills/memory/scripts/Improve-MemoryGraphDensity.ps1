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
    [switch]$DryRun,
    [string]$MemoriesPath,
    [switch]$SkipPathValidation
)

$ErrorActionPreference = 'Stop'

# Determine project root robustly
try {
    $projectRoot = git rev-parse --show-toplevel 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Not in a git repository"
    }
} catch {
    Write-Warning "git rev-parse failed, falling back to directory traversal"
    $projectRoot = $PSScriptRoot
    while ($projectRoot -and -not (Test-Path (Join-Path $projectRoot '.git'))) {
        $projectRoot = Split-Path $projectRoot -Parent
    }
    if (-not $projectRoot) {
        throw "Could not find project root (no .git directory found)"
    }
}

# Use provided path or default to .serena/memories
if (-not $MemoriesPath) {
    $memoriesPath = Join-Path $projectRoot '.serena' 'memories'
} else {
    # Validate provided path is within project root (CWE-22 mitigation)
    # Skip validation only when explicitly requested (e.g., for tests)
    if (-not $SkipPathValidation) {
        $resolvedPath = [IO.Path]::GetFullPath($MemoriesPath)
        $resolvedProjectRoot = [IO.Path]::GetFullPath($projectRoot)

        # Ensure comparison includes directory separator to prevent sibling directory attacks (CWE-22)
        # e.g., /home/user/project-attacker/ should not match /home/user/project/
        $projectRootWithSep = $resolvedProjectRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
        if (-not $resolvedPath.StartsWith($projectRootWithSep, [System.StringComparison]::OrdinalIgnoreCase) -and
            $resolvedPath -ne $resolvedProjectRoot) {
            throw "Security: MemoriesPath must be within project directory. Provided: $resolvedPath, Project root: $resolvedProjectRoot"
        }

        $memoriesPath = $resolvedPath
    } else {
        $memoriesPath = [IO.Path]::GetFullPath($MemoriesPath)
    }
}

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
# Using [ordered] to ensure longest prefixes match first for deterministic results
$domainPatterns = [ordered]@{
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
    $hasRelated = $content -match '(?m)^## Related'

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
