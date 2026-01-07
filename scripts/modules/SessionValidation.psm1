# scripts/modules/SessionValidation.psm1

#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Module for session validation functions (ADR-006: logic in modules, not workflows)

.DESCRIPTION
    Contains reusable validation functions for parsing and validating session logs
    against the canonical SESSION-PROTOCOL.md template.

    Functions:
    - Split-TableRow: Context-aware markdown table row splitter
    - Parse-ChecklistTable: Parses markdown checklist tables into structured objects
    - Normalize-Step: Normalizes checklist step text for comparison
    - Test-MemoryEvidence: Validates memory retrieval evidence (ADR-007)
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Split-TableRow {
  <#
  .SYNOPSIS
    Splits a markdown table row by pipe characters, respecting code spans (backticks).

  .DESCRIPTION
    Character-by-character parser that tracks whether we're inside backticks.
    Only treats pipe characters as column separators when outside code spans.

    Handles:
    - Single backtick code spans: `code|with|pipes`
    - Multiple code spans in same row
    - Empty code spans: ``

    Known limitations:
    - Does not handle escaped backticks (\`)
    - Does not handle nested backticks (rare in practice)

  .PARAMETER Row
    The table row string to split (outer pipes must be removed first)

  .OUTPUTS
    Array of column strings (not trimmed)

  .EXAMPLE
    Split-TableRow ' MUST | Run: `grep "a|b"` | [x] | Done '
    Returns: @(' MUST ', ' Run: `grep "a|b"` ', ' [x] ', ' Done ')
  #>
  param([string]$Row)

  $columns = [System.Collections.Generic.List[string]]::new()
  $currentColumn = [System.Text.StringBuilder]::new()
  $inCodeSpan = $false

  for ($i = 0; $i -lt $Row.Length; $i++) {
    $char = $Row[$i]

    if ($char -eq '`') {
      # Toggle code span state
      $inCodeSpan = -not $inCodeSpan
      [void]$currentColumn.Append($char)
    }
    elseif ($char -eq '|' -and -not $inCodeSpan) {
      # Column separator (only when not in code span)
      $columns.Add($currentColumn.ToString())
      [void]$currentColumn.Clear()
    }
    else {
      # Regular character
      [void]$currentColumn.Append($char)
    }
  }

  # Add final column (always add to handle empty rows and ensure consistent behavior)
  $columns.Add($currentColumn.ToString())

  # Comma operator prevents PowerShell from unwrapping single-element arrays
  , $columns.ToArray()
}

function Parse-ChecklistTable {
  <#
  .SYNOPSIS
    Parses a markdown checklist table into structured objects.

  .DESCRIPTION
    Converts markdown table lines into an array of hashtables with Req, Step, Status, Evidence, and Raw fields.
    Skips header and separator rows. Uses Split-TableRow for context-aware pipe splitting.

  .PARAMETER TableLines
    Array of markdown table lines (including header/separator rows)

  .OUTPUTS
    Array of hashtables with keys: Req, Step, Status, Evidence, Raw

  .EXAMPLE
    $lines = @(
      '| Req | Step | Status | Evidence |',
      '|-----|------|--------|----------|',
      '| MUST | Read file | [x] | Done |'
    )
    Parse-ChecklistTable $lines
  #>
  param([string[]]$TableLines)

  # Returns ordered rows: @{ Req = 'MUST'; Step='...'; Status='x'/' '; Evidence='...' }
  $rows = New-Object System.Collections.Generic.List[hashtable]
  foreach ($line in $TableLines) {
    if ($line -match '^\|\s*-+\s*\|') { continue } # separator row
    if ($line -match '^\|\s*Req\s*\|') { continue } # header row

    # Trim outer pipes and split columns (respecting code spans)
    $innerContent = ($line.Trim() -replace '^\|','' -replace '\|$','')
    $parts = Split-TableRow $innerContent | ForEach-Object { $_.Trim() }
    if ($parts.Count -lt 4) { continue }

    $req = ($parts[0] -replace '\*','').ToUpperInvariant()
    $step = $parts[1]
    $statusRaw = $parts[2]
    $evidence = $parts[3]

    $status = ' '
    if ($statusRaw -match '\[\s*[xX]\s*\]') { $status = 'x' }

    $rows.Add(@{ Req = $req; Step = $step; Status = $status; Evidence = $evidence; Raw = $line })
  }
  # Comma operator prevents PowerShell from unwrapping single-element arrays
  , $rows.ToArray()
}

function Normalize-Step {
  <#
  .SYNOPSIS
    Normalizes checklist step text for comparison.

  .DESCRIPTION
    Removes extra whitespace and asterisks, trims the result.
    Used for comparing checklist steps against canonical template.

  .PARAMETER StepText
    The step text to normalize

  .OUTPUTS
    Normalized string

  .EXAMPLE
    Normalize-Step '  Read **file**  '
    Returns: 'Read file'
  #>
  param([string]$StepText)
  return ($StepText -replace '\s+',' ' -replace '\*','').Trim()
}

function Test-MemoryEvidence {
  <#
  .SYNOPSIS
    Validates that memory-related checklist rows have valid Evidence.

  .DESCRIPTION
    Finds the "memory-index" row in Session Start checklist and verifies:
    1. Evidence column is not empty or placeholder text
    2. Evidence contains memory names (kebab-case identifiers)
    3. Each referenced memory exists in .serena/memories/

  .PARAMETER SessionRows
    Array of hashtables from Parse-ChecklistTable (Session Start rows)

  .PARAMETER RepoRoot
    Path to repository root directory

  .OUTPUTS
    Returns hashtable with validation results:
    - IsValid: $true if validation passed
    - MemoriesFound: Array of memory names found in Evidence
    - MissingMemories: Array of memory names not found on disk
    - ErrorMessage: Explanation if validation failed

  .NOTES
    Related: ADR-007, Issue #729, Session 63 (E2 implementation)
  #>
  [CmdletBinding()]
  param(
    [Parameter(Mandatory)]
    [hashtable[]]$SessionRows,

    [Parameter(Mandatory)]
    [string]$RepoRoot
  )

  $result = @{
    IsValid = $true
    MemoriesFound = @()
    MissingMemories = @()
    ErrorMessage = $null
  }

  # Find the memory-index row (matches "memory-index" in Step column)
  $memoryRow = $SessionRows | Where-Object {
    (Normalize-Step $_.Step) -match 'memory-index.*memories'
  } | Select-Object -First 1

  if (-not $memoryRow) {
    # No memory-index row found - this is a template issue, not evidence issue
    return $result
  }

  $evidence = $memoryRow.Evidence

  # Check for empty or placeholder evidence
  $placeholderPatterns = @(
    '^\s*$',                           # Empty
    '^List memories loaded$',          # Template placeholder
    '^\[.*\]$',                         # Bracketed placeholder like [memories]
    '^-+$'                              # Dashes only
  )

  foreach ($pattern in $placeholderPatterns) {
    if ($evidence -match $pattern) {
      $result.IsValid = $false
      $result.ErrorMessage = "Memory-index Evidence column contains placeholder text: '$evidence'. List actual memory names read (e.g., 'memory-index, skills-pr-review-index')."
      return $result
    }
  }

  # Extract memory names from Evidence (kebab-case identifiers)
  # Pattern: word-word or word-word-word-... (minimum 2 segments)
  $memoryPattern = '[a-z][a-z0-9]*(?:-[a-z0-9]+)+'
  # Wrap in @() to ensure result is always an array (fixes Count property error when single match)
  $foundMemories = @(
    [regex]::Matches($evidence, $memoryPattern, 'IgnoreCase') |
      ForEach-Object { $_.Value.ToLowerInvariant() } |
      Select-Object -Unique
  )

  if ($foundMemories.Count -eq 0) {
    $result.IsValid = $false
    $result.ErrorMessage = "Memory-index Evidence column doesn't contain valid memory names: '$evidence'. Expected format: 'memory-index, skills-pr-review-index, ...' (kebab-case names)."
    return $result
  }

  $result.MemoriesFound = $foundMemories

  # Verify each memory exists in .serena/memories/
  $memoriesDir = Join-Path $RepoRoot ".serena" "memories"
  $missingMemories = [System.Collections.Generic.List[string]]::new()

  foreach ($memName in $foundMemories) {
    $memPath = Join-Path $memoriesDir "$memName.md"
    if (-not (Test-Path -LiteralPath $memPath)) {
      $missingMemories.Add($memName)
    }
  }

  if ($missingMemories.Count -gt 0) {
    $result.MissingMemories = $missingMemories.ToArray()
    $result.IsValid = $false
    $missing = $missingMemories -join ', '
    $result.ErrorMessage = "Memory-index Evidence references memories that don't exist: $missing. Verify memory names or create missing memories in .serena/memories/."
  }

  return $result
}

function Test-RequiredSections {
  <#
  .SYNOPSIS
    Validates that required sections exist in the session log content.
  #>
  [CmdletBinding()]
  param(
    [Parameter(Mandatory)]
    [string]$SessionLogContent,

    [string[]]$RequiredSections = @(
      '## Session Start',
      '## Session End',
      '## Evidence'
    )
  )

  $missingSections = @()
  foreach ($section in $RequiredSections) {
    $pattern = [regex]::Escape($section)
    if ($section -like '##*') {
      $pattern = $pattern -replace '^##','##+'
    }

    if ($SessionLogContent -notmatch $pattern) {
      $missingSections += $section
    }
  }

  return @{
    IsValid = ($missingSections.Count -eq 0)
    MissingSections = $missingSections
    Errors = if ($missingSections.Count -gt 0) {
      @("Missing required sections: $($missingSections -join ', ')")
    } else { @() }
  }
}

function Test-TableStructure {
  <#
  .SYNOPSIS
    Validates checklist table structure.
  #>
  [CmdletBinding()]
  param(
    [Parameter(Mandatory)]
    [string[]]$TableLines
  )

  $errors = @()

  if ($TableLines.Count -lt 2) {
    $errors += 'Table has insufficient rows (need header and separator).'
  } else {
    if ($TableLines[0] -notmatch '^\|\s*Req\s*\|') {
      $errors += 'Table missing header row (expected: | Req | Step | Status | Evidence |).'
    }

    if ($TableLines[1] -notmatch '^\|\s*-+\s*\|') {
      $errors += 'Table missing separator row.'
    }
  }

  $parsedRows = Parse-ChecklistTable -TableLines $TableLines

  foreach ($row in $parsedRows) {
    if (-not $row.Req -or -not $row.Step -or -not $row.Status -or -not $row.Evidence) {
      $errors += "Table row missing required columns: $($row.Raw)"
    }
  }

  return @{
    IsValid = ($errors.Count -eq 0)
    Errors = $errors
    ParsedRows = $parsedRows
  }
}

function Test-PathNormalization {
  <#
  .SYNOPSIS
    Detects absolute paths that violate path normalization rules.
  #>
  [CmdletBinding()]
  param(
    [Parameter(Mandatory)]
    [string]$SessionLogContent
  )

  $absolutePathPatterns = @(
    '[A-Z]:\\',
    '/home/',
    '/Users/'
  )

  $absolutePaths = @()
  foreach ($pattern in $absolutePathPatterns) {
    $matches = [regex]::Matches($SessionLogContent, $pattern)
    foreach ($match in $matches) {
      $start = [Math]::Max(0, $match.Index - 20)
      $length = [Math]::Min(60, $SessionLogContent.Length - $start)
      $context = $SessionLogContent.Substring($start, $length)
      $absolutePaths += $context
    }
  }

  return @{
    IsValid = ($absolutePaths.Count -eq 0)
    AbsolutePaths = $absolutePaths
    Errors = if ($absolutePaths.Count -gt 0) {
      @("Found $($absolutePaths.Count) absolute path(s). Use repo-relative paths.")
    } else { @() }
  }
}

function Test-CommitSHAFormat {
  <#
  .SYNOPSIS
    Validates commit SHA format (7-40 lowercase hex characters).
  #>
  [CmdletBinding()]
  param(
    [Parameter(Mandatory)]
    [AllowEmptyString()]
    [string]$CommitSHA
  )

  if ([string]::IsNullOrWhiteSpace($CommitSHA)) {
    return @{
      IsValid = $false
      Error = 'Commit SHA is empty'
    }
  }

  if ($CommitSHA -notmatch '^[a-f0-9]{7,40}$') {
    if ($CommitSHA -match '^[a-f0-9]{7,12}\s+.+') {
      return @{
        IsValid = $false
        Error = "Commit SHA includes subject line. Use SHA only (e.g., 'abc1234' not 'abc1234 Fix bug')."
      }
    }

    return @{
      IsValid = $false
      Error = "Commit SHA format invalid. Expected 7-40 hex chars, got: '$CommitSHA'"
    }
  }

  return @{
    IsValid = $true
    Error = $null
  }
}

function Test-EvidencePopulation {
  <#
  .SYNOPSIS
    Ensures evidence fields are populated and not placeholders.
  #>
  [CmdletBinding()]
  param(
    [Parameter(Mandatory)]
    [hashtable]$EvidenceFields
  )

  $emptyFields = @()
  $placeholderFields = @()

  $placeholderPatterns = @(
    '^\[.*\]$',
    '^-+$',
    '^\s*$'
  )

  foreach ($field in $EvidenceFields.Keys) {
    $value = $EvidenceFields[$field]

    if ([string]::IsNullOrWhiteSpace($value)) {
      $emptyFields += $field
      continue
    }

    foreach ($pattern in $placeholderPatterns) {
      if ($value -match $pattern) {
        $placeholderFields += "$field='$value'"
        break
      }
    }
  }

  $errors = @()
  if ($emptyFields.Count -gt 0) {
    $errors += "Empty evidence fields: $($emptyFields -join ', ')"
  }
  if ($placeholderFields.Count -gt 0) {
    $errors += "Placeholder evidence: $($placeholderFields -join ', ')"
  }

  return @{
    IsValid = ($errors.Count -eq 0)
    EmptyFields = $emptyFields
    PlaceholderFields = $placeholderFields
    Errors = $errors
  }
}

function Test-TemplateStructure {
  <#
  .SYNOPSIS
    Checkpoint 1: validates template structure for required sections and tables.
  #>
  [CmdletBinding()]
  param(
    [Parameter(Mandatory)]
    [string]$Template
  )

  $errors = @()
  $warnings = @()

  $sectionsResult = Test-RequiredSections -SessionLogContent $Template
  if (-not $sectionsResult.IsValid) {
    $errors += $sectionsResult.Errors
  }

  $sessionStartTable = $Template -match '(?s)## Session Start.*?\|.*?Req.*?\|'
  $sessionEndTable = $Template -match '(?s)## Session End.*?\|.*?Req.*?\|'

  if (-not $sessionStartTable) {
    $errors += 'Session Start section missing checklist table'
  }
  if (-not $sessionEndTable) {
    $errors += 'Session End section missing checklist table'
  }

  $evidenceTable = $Template -match '(?s)## Evidence.*?\|.*?\|'
  if (-not $evidenceTable) {
    $warnings += 'Evidence section missing table (may be populated later)'
  }

  return @{
    IsValid = ($errors.Count -eq 0)
    Checkpoint = 'TemplateStructure'
    Errors = $errors
    Warnings = $warnings
  }
}

function Test-EvidenceFields {
  <#
  .SYNOPSIS
    Checkpoint 2: validates evidence fields and path normalization.
  #>
  [CmdletBinding()]
  param(
    [Parameter(Mandatory)]
    [string]$SessionLog,

    [Parameter(Mandatory)]
    [hashtable]$GitInfo
  )

  $errors = @()
  $warnings = @()
  $fixableIssues = @()

  $evidenceMatch = [regex]::Match($SessionLog, '## Evidence.*?(?=##|$)', [System.Text.RegularExpressions.RegexOptions]::Singleline)
  if (-not $evidenceMatch.Success) {
    $evidenceMatch = [regex]::Match($SessionLog, '## Evidence.*', [System.Text.RegularExpressions.RegexOptions]::Singleline)
  }
  if (-not $evidenceMatch.Success) {
    $errors += 'Evidence section not found'
    return @{
      IsValid = $false
      Checkpoint = 'EvidenceFields'
      Errors = $errors
      Warnings = $warnings
      FixableIssues = $fixableIssues
    }
  }

  $evidenceContent = $evidenceMatch.Value

  $pathResult = Test-PathNormalization -SessionLogContent $evidenceContent
  if (-not $pathResult.IsValid) {
    $errors += $pathResult.Errors
    $fixableIssues += @{
      Type = 'PathNormalization'
      Description = 'Convert absolute paths to repo-relative links'
      AbsolutePaths = $pathResult.AbsolutePaths
    }
  }

  $commitMatch = [regex]::Match($evidenceContent, 'Commit:\s*([^\s\n]+)')
  if ($commitMatch.Success) {
    $commitSHA = $commitMatch.Groups[1].Value
    $shaResult = Test-CommitSHAFormat -CommitSHA $commitSHA
    if (-not $shaResult.IsValid) {
      $errors += $shaResult.Error
      $fixableIssues += @{
        Type = 'CommitSHAFormat'
        Description = "Extract SHA from 'SHA subject' format"
        OldValue = $commitSHA
      }
    }
  } else {
    $warnings += 'Commit SHA not found in Evidence section'
  }

  $evidenceFields = @{
    Branch = [regex]::Match($evidenceContent, 'Branch:\s*([^\n]+)').Groups[1].Value
    Commit = [regex]::Match($evidenceContent, 'Commit:\s*([^\n]+)').Groups[1].Value
    Status = [regex]::Match($evidenceContent, 'Status:\s*([^\n]+)').Groups[1].Value
  }

  $populationResult = Test-EvidencePopulation -EvidenceFields $evidenceFields
  if (-not $populationResult.IsValid) {
    $errors += $populationResult.Errors
    if ($populationResult.EmptyFields.Count -gt 0) {
      $fixableIssues += @{
        Type = 'MissingEvidence'
        Description = 'Populate empty evidence fields from git state'
        EmptyFields = $populationResult.EmptyFields
      }
    }
  }

  return @{
    IsValid = ($errors.Count -eq 0)
    Checkpoint = 'EvidenceFields'
    Errors = $errors
    Warnings = $warnings
    FixableIssues = $fixableIssues
  }
}

function Invoke-FullValidation {
  <#
  .SYNOPSIS
    Checkpoint 3: executes full validation script.
  #>
  [CmdletBinding()]
  param(
    [Parameter(Mandatory)]
    [string]$SessionLogPath,

    [Parameter(Mandatory)]
    [string]$RepoRoot
  )

  $validationScript = Join-Path $RepoRoot 'scripts/Validate-SessionProtocol.ps1'

  if (-not (Test-Path $validationScript)) {
    return @{
      IsValid = $false
      Checkpoint = 'FullValidation'
      Errors = @("Validation script not found: $validationScript")
      Warnings = @()
    }
  }

  try {
    $global:LASTEXITCODE = 0
    $output = & $validationScript -SessionPath $SessionLogPath -Format markdown 2>&1
    $exitCode = if ($null -ne $LASTEXITCODE) { $LASTEXITCODE } else { 0 }

    $errors = $output | Where-Object { $_ -match 'ERROR|FAIL' } | ForEach-Object { $_.ToString() }
    $hasErrors = $errors -ne $null -and $errors.Count -gt 0

    if (($exitCode -eq 0 -or $null -eq $exitCode) -and -not $hasErrors) {
      return @{
        IsValid = $true
        Checkpoint = 'FullValidation'
        Errors = @()
        Warnings = @()
      }
    }

    return @{
      IsValid = $false
      Checkpoint = 'FullValidation'
      Errors = if ($errors) { $errors } else { @('Validation script reported failure with no ERROR/FAIL output.') }
      Warnings = @()
    }
  } catch {
    return @{
      IsValid = $false
      Checkpoint = 'FullValidation'
      Errors = @("Validation script execution failed: $($_.Exception.Message)")
      Warnings = @()
    }
  }
}

# Export all functions
Export-ModuleMember -Function Split-TableRow, Parse-ChecklistTable, Normalize-Step, Test-MemoryEvidence, Test-RequiredSections, Test-TableStructure, Test-PathNormalization, Test-CommitSHAFormat, Test-EvidencePopulation, Test-TemplateStructure, Test-EvidenceFields, Invoke-FullValidation
