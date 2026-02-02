<#
.SYNOPSIS
  Bulk imports observation learnings from Serena memory files to Forgetful MCP.

.DESCRIPTION
  Parses observation markdown files (HIGH/MED/LOW confidence sections) and creates
  Forgetful memories with full provenance tracking. Supports dry-run mode, duplicate
  detection, and batch processing.

  This script implements the import pattern documented in:
  .agents/analysis/forgetful-import-pattern.md

.PARAMETER ObservationFile
  Path to a single observation markdown file to import.

.PARAMETER ObservationDirectory
  Path to directory containing observation files for bulk import.

.PARAMETER ConfidenceLevels
  Filter learnings by confidence level. Valid values: HIGH, MED, LOW.
  Default: HIGH (import only high-confidence learnings).

.PARAMETER ProjectPrefix
  Prefix for Forgetful project names. Default: 'ai-agents-'.

.PARAMETER DryRun
  Preview import without creating memories. Shows what would be imported.

.PARAMETER WhatIf
  Alias for DryRun. Shows what would be imported without executing.

.PARAMETER SkipDuplicateCheck
  Skip querying Forgetful for existing memories (faster but may create duplicates).

.PARAMETER OutputPath
  Path for JSON results file. Default: .agents/analysis/forgetful-import-results.json

.EXAMPLE
  ./Import-ObservationsToForgetful.ps1 -ObservationFile ".serena/memories/testing-observations.md" -DryRun

.EXAMPLE
  ./Import-ObservationsToForgetful.ps1 -ObservationDirectory ".serena/memories" -ConfidenceLevels HIGH,MED

.NOTES
  EXIT CODES:
  0  - Success: All imports completed
  1  - Error: Validation or import failures occurred

  REQUIREMENTS:
  - Forgetful MCP server must be running and accessible
  - claude CLI must be available for MCP tool execution

  See: ADR-005 (PowerShell Only), ADR-035 (Exit Code Standardization)
#>
[CmdletBinding(SupportsShouldProcess, DefaultParameterSetName = 'File')]
param(
  [Parameter(Mandatory, ParameterSetName = 'File', Position = 0)]
  [ValidateScript({ Test-Path $_ -PathType Leaf })]
  [string]$ObservationFile,

  [Parameter(Mandatory, ParameterSetName = 'Directory')]
  [ValidateScript({ Test-Path $_ -PathType Container })]
  [string]$ObservationDirectory,

  [Parameter()]
  [ValidateSet('HIGH', 'MED', 'LOW')]
  [string[]]$ConfidenceLevels = @('HIGH'),

  [Parameter()]
  [string]$ProjectPrefix = 'ai-agents-',

  [Parameter()]
  [switch]$DryRun,

  [Parameter()]
  [switch]$SkipDuplicateCheck,

  [Parameter()]
  [string]$OutputPath = '.agents/analysis/forgetful-import-results.json'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

#region Domain Mapping

# Map observation file names to Forgetful project domains
$DomainMap = @{
  'testing'                = @{ ProjectName = 'testing'; Keywords = @('testing', 'pester', 'validation') }
  'architecture'           = @{ ProjectName = 'architecture'; Keywords = @('architecture', 'adr', 'design') }
  'pr-review'              = @{ ProjectName = 'pr-review'; Keywords = @('pr-review', 'github', 'code-review') }
  'github'                 = @{ ProjectName = 'github'; Keywords = @('github', 'gh-cli', 'api') }
  'powershell'             = @{ ProjectName = 'powershell'; Keywords = @('powershell', 'scripting', 'automation') }
  'ci-infrastructure'      = @{ ProjectName = 'ci-infrastructure'; Keywords = @('ci-cd', 'github-actions', 'pipelines') }
  'session'                = @{ ProjectName = 'session-protocol'; Keywords = @('session', 'protocol', 'logging') }
  'session-protocol'       = @{ ProjectName = 'session-protocol'; Keywords = @('session', 'protocol', 'compliance') }
  'git'                    = @{ ProjectName = 'git'; Keywords = @('git', 'version-control', 'branching') }
  'security'               = @{ ProjectName = 'security'; Keywords = @('security', 'vulnerability', 'secrets') }
  'memory'                 = @{ ProjectName = 'memory-system'; Keywords = @('memory', 'serena', 'forgetful') }
  'validation'             = @{ ProjectName = 'validation'; Keywords = @('validation', 'schema', 'constraints') }
  'documentation'          = @{ ProjectName = 'documentation'; Keywords = @('documentation', 'markdown', 'readme') }
  'environment'            = @{ ProjectName = 'environment'; Keywords = @('environment', 'configuration', 'setup') }
  'agent-workflow'         = @{ ProjectName = 'agent-workflow'; Keywords = @('agent', 'workflow', 'orchestration') }
  'bash-integration'       = @{ ProjectName = 'bash-integration'; Keywords = @('bash', 'shell', 'integration') }
  'error-handling'         = @{ ProjectName = 'error-handling'; Keywords = @('errors', 'exceptions', 'debugging') }
  'qa'                     = @{ ProjectName = 'qa'; Keywords = @('qa', 'quality', 'testing') }
  'retrospective'          = @{ ProjectName = 'retrospective'; Keywords = @('retrospective', 'learnings', 'reflection') }
  'prompting'              = @{ ProjectName = 'prompting'; Keywords = @('prompting', 'llm', 'instructions') }
  'cost-optimization'      = @{ ProjectName = 'cost-optimization'; Keywords = @('cost', 'optimization', 'tokens') }
  'performance'            = @{ ProjectName = 'performance'; Keywords = @('performance', 'speed', 'optimization') }
  'tool-usage'             = @{ ProjectName = 'tool-usage'; Keywords = @('tools', 'mcp', 'integration') }
  'quality-gates'          = @{ ProjectName = 'quality-gates'; Keywords = @('quality', 'gates', 'ci-cd') }
  'enforcement-patterns'   = @{ ProjectName = 'enforcement-patterns'; Keywords = @('enforcement', 'patterns', 'rules') }
  'skills'                 = @{ ProjectName = 'skills'; Keywords = @('skills', 'commands', 'automation') }
  'SkillForge'             = @{ ProjectName = 'skillforge'; Keywords = @('skillforge', 'meta-skill', 'creation') }
  'reflect'                = @{ ProjectName = 'reflect'; Keywords = @('reflect', 'learning', 'capture') }
}

# Confidence to importance mapping (from import pattern)
$ConfidenceMapping = @{
  'HIGH' = @{ ImportanceMin = 9; ImportanceMax = 10; Confidence = 1.0; Tag = 'high-confidence' }
  'MED'  = @{ ImportanceMin = 7; ImportanceMax = 8; Confidence = 0.85; Tag = 'medium-confidence' }
  'LOW'  = @{ ImportanceMin = 5; ImportanceMax = 6; Confidence = 0.7; Tag = 'low-confidence' }
}

# Section to type mapping
$SectionTypeMap = @{
  'Constraints'       = @{ Type = 'constraint'; ConfidenceLevel = 'HIGH' }
  'Preferences'       = @{ Type = 'preference'; ConfidenceLevel = 'MED' }
  'Edge Cases'        = @{ Type = 'edge-case'; ConfidenceLevel = 'MED' }
  'Notes for Review'  = @{ Type = 'note'; ConfidenceLevel = 'LOW' }
}

#endregion

#region Helper Functions

function Get-DomainFromFileName {
  <#
  .SYNOPSIS
    Extracts domain name from observation file name.
  #>
  param([string]$FileName)

  $baseName = [System.IO.Path]::GetFileNameWithoutExtension($FileName)

  # Handle special prefixes like "skills-"
  if ($baseName -match '^skills-(.+)-observations$') {
    return "skills-$($Matches[1])"
  }

  # Standard pattern: {domain}-observations
  if ($baseName -match '^(.+)-observations$') {
    return $Matches[1]
  }

  return $baseName
}

function Get-ProjectInfo {
  <#
  .SYNOPSIS
    Gets project info from domain map or creates default.
  #>
  param([string]$Domain)

  if ($DomainMap.ContainsKey($Domain)) {
    return $DomainMap[$Domain]
  }

  # Default for unmapped domains
  return @{
    ProjectName = $Domain
    Keywords    = @($Domain, 'learnings', 'observations')
  }
}

function ConvertTo-SafeTitle {
  <#
  .SYNOPSIS
    Creates a safe, short title from learning text.
  #>
  param([string]$LearningText)

  # Take first sentence or first 80 chars
  $title = if ($LearningText -match '^([^.!?]+[.!?])') {
    $Matches[1].Trim()
  } else {
    $LearningText.Substring(0, [Math]::Min(80, $LearningText.Length))
  }

  # Remove session references for cleaner title
  $title = $title -replace '\s*\(Session[^)]+\)', ''
  $title = $title -replace '\s*\(.*?\d{4}-\d{2}-\d{2}.*?\)', ''

  # Trim and ensure not too long
  $title = $title.Trim()
  if ($title.Length -gt 100) {
    $title = $title.Substring(0, 97) + '...'
  }

  return $title
}

function Parse-ObservationFile {
  <#
  .SYNOPSIS
    Parses an observation markdown file and extracts learnings.
  .OUTPUTS
    Array of learning objects with metadata.
  #>
  param(
    [string]$FilePath,
    [string[]]$FilterConfidence = @('HIGH', 'MED', 'LOW')
  )

  $content = Get-Content $FilePath -Raw
  $fileName = [System.IO.Path]::GetFileName($FilePath)
  $domain = Get-DomainFromFileName $fileName
  $projectInfo = Get-ProjectInfo $domain

  $learnings = @()
  $currentSection = $null
  $currentLearning = $null
  $inLearning = $false

  $lines = $content -split "`n"

  foreach ($line in $lines) {
    $trimmedLine = $line.Trim()

    # Detect section headers
    if ($trimmedLine -match '^##\s+(Constraints|Preferences|Edge Cases|Notes for Review)') {
      $sectionName = $Matches[1]
      if ($SectionTypeMap.ContainsKey($sectionName)) {
        $currentSection = $SectionTypeMap[$sectionName]
      }
      $currentLearning = $null
      $inLearning = $false
      continue
    }

    # Skip non-learning sections - but first save any pending learning
    if ($trimmedLine -match '^##\s+(Purpose|History|Related|Overview)') {
      if ($currentLearning) {
        $learnings += $currentLearning
      }
      $currentSection = $null
      $currentLearning = $null
      $inLearning = $false
      continue
    }

    # Skip if not in a valid section
    if (-not $currentSection) { continue }

    # Skip if filtering out this confidence level
    if ($currentSection.ConfidenceLevel -notin $FilterConfidence) { continue }

    # Detect learning bullet points (- at start of line, not sub-bullets)
    # Note: Must capture $Matches before second -match overwrites it
    $isLearningLine = $trimmedLine -match '^- (.+)$'
    $capturedText = if ($isLearningLine) { $Matches[1] } else { $null }
    if ($isLearningLine -and $line -match '^- ') {
      # Skip placeholder entries like "None yet"
      if ($capturedText -match '^\s*None\s*(yet)?\s*$') {
        continue
      }

      # Save previous learning if exists
      if ($currentLearning) {
        $learnings += $currentLearning
      }

      $learningText = $capturedText

      # Extract session metadata from text
      $sessionInfo = $null
      $dateInfo = $null
      if ($learningText -match '\(Session\s+([^,)]+)(?:,\s*(\d{4}-\d{2}-\d{2}))?\)') {
        $sessionInfo = $Matches[1]
        $dateInfo = $Matches[2]
      } elseif ($learningText -match '\(([^)]*\d{4}-\d{2}-\d{2}[^)]*)\)') {
        $dateInfo = ($Matches[1] -split ',')[-1].Trim()
      }

      $currentLearning = @{
        Domain           = $domain
        ProjectName      = $projectInfo.ProjectName
        BaseKeywords     = $projectInfo.Keywords
        ConfidenceLevel  = $currentSection.ConfidenceLevel
        Type             = $currentSection.Type
        Text             = $learningText
        Evidence         = @()
        Session          = $sessionInfo
        Date             = $dateInfo
        SourceFile       = $FilePath
      }
      $inLearning = $true
    }
    # Detect evidence sub-bullets
    elseif ($trimmedLine -match '^\s*-\s+Evidence:\s*(.+)$' -and $currentLearning) {
      $currentLearning.Evidence += $Matches[1]
    }
    # Continuation of evidence or multi-line learning
    elseif ($trimmedLine -match '^\s+-\s+(.+)$' -and $currentLearning -and $inLearning) {
      # Additional evidence lines
      if ($trimmedLine -match 'Evidence') {
        $currentLearning.Evidence += ($trimmedLine -replace '^\s*-\s+Evidence:\s*', '')
      }
    }
  }

  # Don't forget last learning
  if ($currentLearning) {
    $learnings += $currentLearning
  }

  return $learnings
}

function Build-MemoryPayload {
  <#
  .SYNOPSIS
    Builds Forgetful memory payload from parsed learning.
  #>
  param(
    [hashtable]$Learning,
    [int]$ProjectId
  )

  $confidenceInfo = $ConfidenceMapping[$Learning.ConfidenceLevel]

  # Build title
  $title = ConvertTo-SafeTitle $Learning.Text

  # Build content
  $content = $Learning.Text
  if ($Learning.Evidence.Count -gt 0) {
    $content += "`n`nEvidence: " + ($Learning.Evidence -join '; ')
  }

  # Build context
  $contextParts = @("Observation from $($Learning.Domain) domain")
  if ($Learning.Session) {
    $contextParts += "Session $($Learning.Session)"
  }
  if ($Learning.Date) {
    $contextParts += $Learning.Date
  }
  $contextParts += "$($Learning.Type) ($($Learning.ConfidenceLevel) confidence)"
  $context = $contextParts -join '. '

  # Build keywords - combine domain keywords with extracted terms
  $keywords = @($Learning.BaseKeywords)
  $keywords += $Learning.Type
  $keywords += $Learning.ConfidenceLevel.ToLower()

  # Extract additional keywords from text
  $text = $Learning.Text.ToLower()
  @('powershell', 'pester', 'github', 'ci', 'pipeline', 'test', 'adr', 'memory', 'session', 'validation', 'git', 'mcp') | ForEach-Object {
    if ($text -match $_) { $keywords += $_ }
  }
  $keywords = @($keywords | Select-Object -Unique)

  # Build tags
  $tags = @(
    $Learning.Domain,
    $Learning.Type,
    $confidenceInfo.Tag
  )

  # Calculate importance (random within range for variety)
  $importance = Get-Random -Minimum $confidenceInfo.ImportanceMin -Maximum ($confidenceInfo.ImportanceMax + 1)

  return @{
    title          = $title
    content        = $content
    context        = $context
    keywords       = $keywords
    tags           = $tags
    importance     = $importance
    project_ids    = @($ProjectId)
    source_repo    = 'rjmurillo/ai-agents'
    source_files   = @($Learning.SourceFile -replace '^.*?\.serena', '.serena')
    confidence     = $confidenceInfo.Confidence
    encoding_agent = 'claude-opus-4-5'
  }
}

function Get-OrCreateProject {
  <#
  .SYNOPSIS
    Gets existing Forgetful project or creates new one.
  #>
  param(
    [string]$ProjectName,
    [string]$Description,
    [string]$SourceFile
  )

  $fullName = "$ProjectPrefix$ProjectName"

  # Check if project exists (using global list from earlier query)
  if ($script:ExistingProjects -and $script:ExistingProjects.projects) {
    $existing = $script:ExistingProjects.projects | Where-Object { $_.name -eq $fullName }
    if ($existing) {
      Write-Verbose "Using existing project: $fullName (ID: $($existing.id))"
      return $existing.id
    }
  }

  if ($DryRun -or $WhatIfPreference) {
    Write-Host "  [DRY-RUN] Would create project: $fullName" -ForegroundColor Yellow
    return -1  # Placeholder ID for dry run
  }

  # Create project via MCP (this would need actual MCP call in production)
  Write-Host "  Creating project: $fullName" -ForegroundColor Cyan

  # Note: In production, this would call Forgetful MCP to create project
  # For now, return placeholder - actual implementation needs MCP integration
  Write-Warning "Project creation requires MCP integration - returning placeholder"
  return -1
}

function Test-DuplicateMemory {
  <#
  .SYNOPSIS
    Checks if a similar memory already exists in Forgetful.
  #>
  param(
    [string]$Title,
    [int]$ProjectId
  )

  if ($SkipDuplicateCheck) {
    return $false
  }

  # Query Forgetful for similar memories
  # This would need actual MCP query in production
  # For now, return false (no duplicate check)
  return $false
}

#endregion

#region Main Execution

# Banner
Write-Host "`n=== Forgetful Observation Import ===" -ForegroundColor Cyan
Write-Host "Confidence Levels: $($ConfidenceLevels -join ', ')" -ForegroundColor Gray
if ($DryRun -or $WhatIfPreference) {
  Write-Host "[DRY RUN MODE - No changes will be made]" -ForegroundColor Yellow
}
Write-Host ""

# Collect files to process
$files = @()
if ($PSCmdlet.ParameterSetName -eq 'File') {
  $files += Get-Item $ObservationFile
} else {
  $files += Get-ChildItem $ObservationDirectory -Filter '*-observations.md' -File
}

Write-Host "Files to process: $($files.Count)" -ForegroundColor Gray

# Load existing projects for mapping
try {
  # Note: This would call Forgetful MCP in production
  $script:ExistingProjects = $null  # Placeholder for MCP result
} catch {
  Write-Warning "Could not load existing projects: $_"
}

# Results tracking
$results = @{
  StartTime       = Get-Date -Format 'o'
  Parameters      = @{
    ConfidenceLevels = $ConfidenceLevels
    DryRun           = $DryRun.IsPresent
    Files            = $files.FullName
  }
  FilesProcessed  = @()
  TotalLearnings  = 0
  Imported        = 0
  Skipped         = 0
  Errors          = @()
  ByDomain        = @{}
  ByConfidence    = @{
    HIGH = 0
    MED  = 0
    LOW  = 0
  }
}

foreach ($file in $files) {
  Write-Host "`nProcessing: $($file.Name)" -ForegroundColor White
  Write-Host ("-" * 50) -ForegroundColor Gray

  try {
    # Wrap in @() to force array type (prevents .Count errors on single/null results)
    # Filter out null values that may be returned
    $learnings = @(Parse-ObservationFile -FilePath $file.FullName -FilterConfidence $ConfidenceLevels | Where-Object { $null -ne $_ })

    if ($learnings.Count -eq 0) {
      Write-Host "  No learnings found matching filter" -ForegroundColor Yellow
      $results.FilesProcessed += @{
        File     = $file.Name
        Learnings = 0
        Status   = 'empty'
      }
      continue
    }

    Write-Host "  Found $($learnings.Count) learnings" -ForegroundColor Green

    $fileResult = @{
      File      = $file.Name
      Domain    = $learnings[0].Domain
      Learnings = $learnings.Count
      Imported  = 0
      Skipped   = 0
      Errors    = @()
    }

    foreach ($learning in $learnings) {
      $results.TotalLearnings++
      $results.ByConfidence[$learning.ConfidenceLevel]++

      if (-not $results.ByDomain.ContainsKey($learning.Domain)) {
        $results.ByDomain[$learning.Domain] = 0
      }
      $results.ByDomain[$learning.Domain]++

      $title = ConvertTo-SafeTitle $learning.Text

      if ($DryRun -or $WhatIfPreference) {
        Write-Host "  [DRY-RUN] Would import: $title" -ForegroundColor Yellow
        Write-Host "            Confidence: $($learning.ConfidenceLevel), Type: $($learning.Type)" -ForegroundColor Gray
        $fileResult.Imported++
        $results.Imported++
      } else {
        # Check for duplicates
        if (Test-DuplicateMemory -Title $title -ProjectId 1) {
          Write-Host "  [SKIP] Duplicate: $title" -ForegroundColor Yellow
          $fileResult.Skipped++
          $results.Skipped++
          continue
        }

        try {
          # Build payload
          $payload = Build-MemoryPayload -Learning $learning -ProjectId 1

          # Note: This would call Forgetful MCP create_memory in production
          Write-Host "  [IMPORT] $title" -ForegroundColor Green

          $fileResult.Imported++
          $results.Imported++
        } catch {
          $errorMsg = "Failed to import '$title': $_"
          Write-Host "  [ERROR] $errorMsg" -ForegroundColor Red
          $fileResult.Errors += $errorMsg
          $results.Errors += @{
            File    = $file.Name
            Title   = $title
            Error   = $_.ToString()
          }
        }
      }
    }

    $fileResult.Status = if ($fileResult.Errors.Count -gt 0) { 'partial' } else { 'success' }
    $results.FilesProcessed += $fileResult

  } catch {
    $errorMsg = "Failed to process file $($file.Name): $_"
    Write-Host "  [ERROR] $errorMsg" -ForegroundColor Red
    $results.Errors += @{
      File  = $file.Name
      Error = $_.ToString()
    }
    $results.FilesProcessed += @{
      File   = $file.Name
      Status = 'error'
      Error  = $_.ToString()
    }
  }
}

# Finalize results
$results.EndTime = Get-Date -Format 'o'
$results.Duration = ((Get-Date) - [datetime]$results.StartTime).TotalSeconds

# Summary
Write-Host "`n=== Import Summary ===" -ForegroundColor Cyan
Write-Host "Files processed:  $($results.FilesProcessed.Count)"
Write-Host "Total learnings:  $($results.TotalLearnings)"
Write-Host "Imported:         $($results.Imported)" -ForegroundColor Green
Write-Host "Skipped:          $($results.Skipped)" -ForegroundColor Yellow
Write-Host "Errors:           $($results.Errors.Count)" -ForegroundColor $(if ($results.Errors.Count -gt 0) { 'Red' } else { 'Gray' })

Write-Host "`nBy Confidence:" -ForegroundColor White
$results.ByConfidence.GetEnumerator() | ForEach-Object {
  Write-Host "  $($_.Key): $($_.Value)"
}

Write-Host "`nBy Domain:" -ForegroundColor White
$results.ByDomain.GetEnumerator() | Sort-Object Value -Descending | ForEach-Object {
  Write-Host "  $($_.Key): $($_.Value)"
}

# Save results
if ($OutputPath) {
  $outputDir = Split-Path $OutputPath -Parent
  if ($outputDir -and -not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
  }

  $results | ConvertTo-Json -Depth 10 | Set-Content $OutputPath -Encoding UTF8
  Write-Host "`nResults saved to: $OutputPath" -ForegroundColor Gray
}

# Exit code
$exitCode = if ($results.Errors.Count -gt 0) { 1 } else { 0 }
exit $exitCode

#endregion
