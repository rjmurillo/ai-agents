#!/usr/bin/env pwsh
<#
.SYNOPSIS
Split bundled skill files into individual files per ADR-017.

.DESCRIPTION
Reads bundled skill files containing multiple skills and splits them into
individual files following the naming convention: domain-###-topic.md

.PARAMETER BundledFilesDir
Directory containing bundled skill files. Default: .serena/memories/

.PARAMETER DryRun
Show what would be done without making changes.
#>

[CmdletBinding()]
param(
    [string]$BundledFilesDir = ".serena/memories",
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

# List of bundled files to process
$bundledFiles = @(
    "documentation-fallback-pattern.md",
    "documentation-migration-search.md",
    "documentation-self-contained.md",
    "implementation-test-discovery.md",
    "iteration-5-checkpoint-skills.md",
    "labeler-matcher-types.md",
    "labeler-negation-patterns.md",
    "phase3-consistency-skills.md",
    "phase4-handoff-validation-skills.md",
    "planning-self-contained.md",
    "pr-review-bot-triage.md",
    "pr-review-false-positives.md",
    "pr-review-noise-skills.md",
    "security-defensive-coding.md",
    "security-review-enforcement.md",
    "security-toctou-defense.md",
    "skills-agent-workflow-phase3.md",
    "skills-analysis.md",
    "skills-architecture.md",
    "skills-definition-of-done.md",
    "skills-design.md",
    "skills-edit.md",
    "skills-execution.md",
    "skills-github-actions-labeler.md",
    "skills-governance.md",
    "skills-implementation.md",
    "skills-jq-json-parsing.md",
    "skills-maintenance.md",
    "skills-orchestration.md",
    "skills-planning.md",
    "skills-powershell.md",
    "skills-qa.md",
    "skills-review.md",
    "skills-security.md",
    "skills-session-initialization.md",
    "skills-utilities.md",
    "skills-validation.md"
)

$totalSkills = 0
$filesToDelete = @()

foreach ($file in $bundledFiles) {
    $path = Join-Path $BundledFilesDir $file
    
    if (-not (Test-Path $path)) {
        Write-Warning "File not found: $path"
        continue
    }
    
    Write-Host "Processing: $file" -ForegroundColor Cyan
    
    $content = Get-Content -Path $path -Raw
    
    # Find all skill headers
    $skillMatches = [regex]::Matches($content, '(?m)^## (Skill-([A-Za-z\-]+)-(\d+)):\s*([^\n]+)')
    
    if ($skillMatches.Count -eq 0) {
        Write-Warning "  No skills found in $file"
        continue
    }
    
    Write-Host "  Found $($skillMatches.Count) skills"
    $totalSkills += $skillMatches.Count
    
    for ($i = 0; $i -lt $skillMatches.Count; $i++) {
        $match = $skillMatches[$i]
        $fullSkillName = $match.Groups[1].Value
        $domain = $match.Groups[2].Value.ToLower()
        $number = $match.Groups[3].Value.PadLeft(3, '0')
        $statement = $match.Groups[4].Value.Trim()
        
        # Extract content from this skill to the next skill or end
        $startIndex = $match.Index
        $endIndex = if ($i -lt ($skillMatches.Count - 1)) {
            $skillMatches[$i + 1].Index
        } else {
            # Find ## Related section or end of file
            $relatedMatch = [regex]::Match($content.Substring($startIndex), '(?m)^## Related')
            if ($relatedMatch.Success) {
                $startIndex + $relatedMatch.Index
            } else {
                $content.Length
            }
        }
        
        $skillContent = $content.Substring($startIndex, $endIndex - $startIndex).Trim()
        
        # Generate topic from statement
        $topic = $statement -replace '[^a-zA-Z0-9\s]', '' -replace '\s+', '-' -replace '^-+|-+$', ''
        $topic = $topic.ToLower()
        if ($topic.Length -gt 50) {
            $topic = $topic.Substring(0, 50) -replace '-+$', ''
        }
        
        # Create filename
        $outputFile = "$domain-$number-$topic.md"
        $outputPath = Join-Path $BundledFilesDir $outputFile
        
        # Create header with proper title
        $domainText = $domain -replace '-', ' '
        $topicText = $topic -replace '-', ' '
        $domainTitle = (Get-Culture).TextInfo.ToTitleCase($domainText)
        $topicTitle = (Get-Culture).TextInfo.ToTitleCase($topicText)
        $fileHeader = "# $domainTitle`: $topicTitle`n`n"
        
        $finalContent = $fileHeader + $skillContent
        
        if ($DryRun) {
            Write-Host "    Would create: $outputFile" -ForegroundColor Gray
        } else {
            $finalContent | Out-File -FilePath $outputPath -Encoding utf8 -NoNewline
            Write-Host "    Created: $outputFile" -ForegroundColor Green
        }
    }
    
    $filesToDelete += $path
}

Write-Host "`nSummary:" -ForegroundColor Cyan
Write-Host "  Total bundled files processed: $($bundledFiles.Count)"
Write-Host "  Total skills extracted: $totalSkills"

if (-not $DryRun) {
    Write-Host "`nDeleting bundled files..." -ForegroundColor Yellow
    foreach ($file in $filesToDelete) {
        if (Test-Path $file) {
            Remove-Item -Path $file -Force
            Write-Host "  Deleted: $(Split-Path -Leaf $file)" -ForegroundColor Red
        }
    }
}

Write-Host "`nDone!" -ForegroundColor Green
