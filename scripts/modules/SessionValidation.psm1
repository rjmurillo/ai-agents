# scripts/modules/SessionValidation.psm1

#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Module for session validation functions (ADR-006: logic in modules, not workflows)

.DESCRIPTION
    Contains reusable validation functions for parsing and validating session logs
    against the canonical SESSION-PROTOCOL.md template.

  Helper functions (Split-TableRow, Parse-ChecklistTable, Normalize-Step, Test-* helpers) normalize tables and evidence fields.
  Checkpoint functions (Test-TemplateStructure, Test-EvidenceFields, Invoke-FullValidation) wrap protocol gates for phase-aligned validation.
  Validation functions (e.g., Test-SessionLogExists, Test-MustRequirements) power granular checks used by the session protocol script.

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
    String[] of column values (not trimmed)

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
    Hashtable[] with keys: Req (string), Step (string), Status (string), Evidence (string), Raw (string)

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
    String containing normalized step text

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
    Hashtable with keys: IsValid (bool), Errors (string[]), Warnings (string[]), FixableIssues (object[])

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

  $errors = @()
  $warnings = @()
  $fixableIssues = @()
  $returnResult = {
    return @{
      IsValid = ($errors.Count -eq 0)
      Errors = $errors
      Warnings = $warnings
      FixableIssues = $fixableIssues
    }
  }

  # Find the memory-index row (matches "memory-index" in Step column)
  $memoryRow = $SessionRows | Where-Object {
    (Normalize-Step $_.Step) -match 'memory-index.*memories'
  } | Select-Object -First 1

  if (-not $memoryRow) {
    # No memory-index row found - this is a template issue, not evidence issue
    return @{
      IsValid = $true
      Errors = $errors
      Warnings = $warnings
      FixableIssues = $fixableIssues
      ErrorMessage = ''
      MemoriesFound = @()
    }
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
      $errors += "Memory-index Evidence column contains placeholder text: '$evidence'. List actual memory names read (e.g., 'memory-index, skills-pr-review-index')."
      return @{
        IsValid = $false
        Errors = $errors
        Warnings = $warnings
        FixableIssues = $fixableIssues
        ErrorMessage = ($errors -join "`n")
        MemoriesFound = @()
      }
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
    $errors += "Memory-index Evidence column doesn't contain valid memory names: '$evidence'. Expected format: 'memory-index, skills-pr-review-index, ...' (kebab-case names)."
    return @{
      IsValid = $false
      Errors = $errors
      Warnings = $warnings
      FixableIssues = $fixableIssues
      ErrorMessage = ($errors -join "`n")
      MemoriesFound = @()
    }
  }

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
    $missing = $missingMemories -join ', '
    $errors += "Memory-index Evidence references memories that don't exist: $missing. Verify memory names or create missing memories in .serena/memories/."
    $fixableIssues += @{
      Type = 'MissingMemories'
      Description = 'Create or correct referenced memories in .serena/memories/'
      Memories = $missingMemories.ToArray()
    }
  }

  return @{
    IsValid = ($errors.Count -eq 0)
    Errors = $errors
    Warnings = $warnings
    FixableIssues = $fixableIssues
    ErrorMessage = ($errors -join "`n")
    MemoriesFound = $foundMemories
  }
}

function Test-RequiredSections {
  <#
  .SYNOPSIS
    Validates that required sections exist in the session log content.

  .OUTPUTS
    Hashtable with keys: IsValid (bool), Errors (string[]), Warnings (string[]), FixableIssues (object[])
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

  $errors = @()
  if ($missingSections.Count -gt 0) {
    $errors += "Missing required sections: $($missingSections -join ', ')"
  }

  return @{
    IsValid = ($errors.Count -eq 0)
    Errors = $errors
    Warnings = @()
    FixableIssues = @()
  }
}

function Test-TableStructure {
  <#
  .SYNOPSIS
    Validates checklist table structure.

  .OUTPUTS
    Hashtable with keys: IsValid (bool), Errors (string[]), Warnings (string[]), FixableIssues (object[])
  #>
  [CmdletBinding()]
  param(
    [Parameter(Mandatory)]
    [string[]]$TableLines
  )

  $errors = @()
  $warnings = @()
  $fixableIssues = @()

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

  if ($errors.Count -gt 0) {
    $fixableIssues += @{ Type = 'TableStructure'; Description = 'Fix malformed checklist table rows'; Rows = $parsedRows }
  }

  return @{
    IsValid = ($errors.Count -eq 0)
    Errors = $errors
    Warnings = $warnings
    FixableIssues = $fixableIssues
  }
}

function Test-PathNormalization {
  <#
  .SYNOPSIS
    Detects absolute paths that violate path normalization rules.

  .OUTPUTS
    Hashtable with keys: IsValid (bool), Errors (string[]), Warnings (string[]), FixableIssues (object[])
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
    $absoluteMatches = [regex]::Matches($SessionLogContent, $pattern)
    foreach ($match in $absoluteMatches) {
      $start = [Math]::Max(0, $match.Index - 20)
      $length = [Math]::Min(60, $SessionLogContent.Length - $start)
      $context = $SessionLogContent.Substring($start, $length)
      $absolutePaths += $context
    }
  }

  $errors = @()
  $fixableIssues = @()

  if ($absolutePaths.Count -gt 0) {
    $errors += "Found $($absolutePaths.Count) absolute path(s). Use repo-relative paths."
    $fixableIssues += @{
      Type = 'PathNormalization'
      Description = 'Convert absolute paths to repo-relative links'
      AbsolutePaths = $absolutePaths
    }
  }

  return @{
    IsValid = ($errors.Count -eq 0)
    Errors = $errors
    Warnings = @()
    FixableIssues = $fixableIssues
  }
}

function Test-CommitSHAFormat {
  <#
  .SYNOPSIS
    Validates commit SHA format (7-40 lowercase hex characters).

  .OUTPUTS
    Hashtable with keys: IsValid (bool), Errors (string[]), Warnings (string[]), FixableIssues (object[])
  #>
  [CmdletBinding()]
  param(
    [Parameter(Mandatory)]
    [AllowEmptyString()]
    [string]$CommitSHA
  )

  $errors = @()
  $warnings = @()
  $fixableIssues = @()

  if ([string]::IsNullOrWhiteSpace($CommitSHA)) {
    $errors += 'Commit SHA is empty'
  }

  if ($CommitSHA -and $CommitSHA -notmatch '^[a-f0-9]{7,40}$') {
    if ($CommitSHA -match '^[a-f0-9]{7,12}\s+.+') {
      $errors += "Commit SHA includes subject line. Use SHA only (e.g., 'abc1234' not 'abc1234 Fix bug')."
    } else {
      $errors += "Commit SHA format invalid. Expected 7-40 hex chars, got: '$CommitSHA'"
    }
  }

  return @{
    IsValid = ($errors.Count -eq 0)
    Errors = $errors
    Warnings = $warnings
    FixableIssues = $fixableIssues
  }
}

function Test-EvidencePopulation {
  <#
  .SYNOPSIS
    Ensures evidence fields are populated and not placeholders.

  .OUTPUTS
    Hashtable with keys: IsValid (bool), Errors (string[]), Warnings (string[]), FixableIssues (object[])
  #>
  [CmdletBinding()]
  param(
    [Parameter(Mandatory)]
    [hashtable]$EvidenceFields
  )

  $emptyFields = @()
  $placeholderFields = @()
  $warnings = @()
  $fixableIssues = @()

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

  if ($emptyFields.Count -gt 0) {
    $fixableIssues += @{ Type = 'MissingEvidence'; Description = 'Populate empty evidence fields'; Fields = $emptyFields }
  }

  if ($placeholderFields.Count -gt 0) {
    $fixableIssues += @{ Type = 'PlaceholderEvidence'; Description = 'Replace placeholders with real values'; Fields = $placeholderFields }
  }

  return @{
    IsValid = ($errors.Count -eq 0)
    Errors = $errors
    Warnings = $warnings
    FixableIssues = $fixableIssues
  }
}

#region Validation Functions

function Test-SessionLogExists {
  <#
  .SYNOPSIS
    Validates that session log file exists and has correct naming pattern.

  .OUTPUTS
    Hashtable with keys: IsValid (bool), Errors (string[]), Warnings (string[]), FixableIssues (object[])
  #>
  [CmdletBinding()]
  param([string]$FilePath)

  $errors = @()
  $warnings = @()
  $fixableIssues = @()

  if (Test-Path $FilePath) {
    $fileName = Split-Path -Leaf $FilePath
    if ($fileName -notmatch '^\d{4}-\d{2}-\d{2}-session-\d+(-.+)?\.md$') {
      $errors += "Session log naming violation: $fileName (expected: YYYY-MM-DD-session-N.md or YYYY-MM-DD-session-N-description.md)"
    }
  } else {
    $errors += "Session log file does not exist: $FilePath"
  }

  return @{
    IsValid = ($errors.Count -eq 0)
    Errors = $errors
    Warnings = $warnings
    FixableIssues = $fixableIssues
  }
}

function Test-ProtocolComplianceSection {
  <#
  .SYNOPSIS
    Validates that session log contains Protocol Compliance section.

  .OUTPUTS
    Hashtable with keys: IsValid (bool), Errors (string[]), Warnings (string[]), FixableIssues (object[])
  #>
  [CmdletBinding()]
  param([string]$Content)

  $errors = @()
  $warnings = @()
  $fixableIssues = @()

  if ($Content -notmatch '(?i)##\s*Protocol\s+Compliance') {
    $errors += "Missing 'Protocol Compliance' section"
  }

  if ($Content -notmatch '(?i)Session\s+Start.*COMPLETE\s+ALL|Start.*before.*work') {
    $errors += "Missing Session Start checklist header"
  }

  if ($Content -notmatch '(?i)Session\s+End.*COMPLETE\s+ALL|End.*before.*closing') {
    $errors += "Missing Session End checklist header"
  }

  return @{
    IsValid = ($errors.Count -eq 0)
    Errors = $errors
    Warnings = $warnings
    FixableIssues = $fixableIssues
  }
}

function Test-MustRequirements {
  <#
  .SYNOPSIS
    Validates that all MUST requirements in the session log are checked.

  .OUTPUTS
    Hashtable with keys: IsValid (bool), Errors (string[]), Warnings (string[]), FixableIssues (object[])
  #>
  [CmdletBinding()]
  param([string]$Content)

  $totalMust = 0
  $completedMust = 0
  $incompleteMust = @()
  $errors = @()
  $warnings = @()
  $fixableIssues = @()

  $mustMatches = [regex]::Matches($Content, '\|\s*\*?\*?MUST\*?\*?\s*\|([^|]+)\|\s*\[([x ])\]')

  foreach ($match in $mustMatches) {
    $totalMust++
    $description = $match.Groups[1].Value.Trim()
    $isComplete = $match.Groups[2].Value -eq 'x'

    if ($isComplete) {
      $completedMust++
    } else {
      $incompleteMust += $description
    }
  }

  if ($mustMatches.Count -eq 0) {
    $tableMatches = [regex]::Matches($Content, '\|\s*\*?\*?MUST\*?\*?\s*\|[^|]+\|\s*\[([xX ])\]\s*\|')
    foreach ($match in $tableMatches) {
      $totalMust++
      $isComplete = $match.Groups[1].Value.ToLowerInvariant() -eq 'x'
      if (-not $isComplete) {
        $incompleteMust += "(table row)"
      } else {
        $completedMust++
      }
    }
  }

  if ($incompleteMust.Count -gt 0) {
    $errors += "MUST requirements: $($incompleteMust.Count)/$totalMust incomplete"
    foreach ($incomplete in $incompleteMust) {
      $errors += "  - $incomplete"
    }
  }

  return @{
    IsValid = ($errors.Count -eq 0)
    Errors = $errors
    Warnings = $warnings
    FixableIssues = $fixableIssues
  }
}

function Test-MustNotRequirements {
  <#
  .SYNOPSIS
    Validates that MUST NOT requirements are verified (checked).

  .DESCRIPTION
    MUST NOT requirements represent prohibited actions per SESSION-PROTOCOL.md.
    Checkbox semantics for MUST NOT:
    - [x] = Verified compliance (confirmed did NOT perform prohibited action)
    - [ ] = Not verified (unknown if prohibited action was performed)

    Examples: "MUST NOT Update HANDOFF.md", "MUST NOT Skip validation"

  .PARAMETER Content
    Session log content to validate

  .OUTPUTS
    Hashtable with keys: IsValid (bool), Errors (string[]), Warnings (string[]), FixableIssues (object[])
  #>
  [CmdletBinding()]
  param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$Content
  )

  $totalMustNot = 0
  $compliant = 0
  $violations = @()
  $errors = @()
  $warnings = @()
  $fixableIssues = @()

  $mustNotMatches = [regex]::Matches($Content, '\|\s*\*?\*?MUST\s+NOT\*?\*?\s*\|([^|]+)\|\s*\[([x ])\]')

  foreach ($match in $mustNotMatches) {
    $totalMustNot++
    $description = $match.Groups[1].Value.Trim()
    $isChecked = $match.Groups[2].Value -eq 'x'

    if ($isChecked) {
      $compliant++
    } else {
      $violations += $description
    }
  }

  if ($mustNotMatches.Count -eq 0) {
    $tableMatches = [regex]::Matches($Content, '\|\s*\*?\*?MUST\s+NOT\*?\*?\s*\|[^|]+\|\s*\[([xX ])\]\s*\|')
    foreach ($match in $tableMatches) {
      $totalMustNot++
      $isChecked = $match.Groups[1].Value.ToLowerInvariant() -eq 'x'
      if ($isChecked) {
        $compliant++
      } else {
        $violations += "(table row)"
      }
    }
  }

  if ($violations.Count -gt 0) {
    $errors += "MUST NOT requirements: $($violations.Count)/$totalMustNot unverified"
    foreach ($unverified in $violations) {
      $errors += "  - NOT VERIFIED: $unverified"
    }
  }

  return @{
    IsValid = ($errors.Count -eq 0)
    Errors = $errors
    Warnings = $warnings
    FixableIssues = $fixableIssues
  }
}

function Test-HandoffUpdated {
  <#
  .SYNOPSIS
    Checks whether HANDOFF.md was modified during the session (violation of SESSION-PROTOCOL.md).
    Per protocol: "MUST NOT update HANDOFF.md". Session context goes to log and Serena memory.

  .NOTES
    Prefers git diff for reliable detection. Falls back to filesystem timestamps in non-git environments.
    In shallow clones where git diff fails, validation fails rather than using unreliable timestamps.

  .OUTPUTS
    Hashtable with keys: IsValid (bool), Errors (string[]), Warnings (string[]), FixableIssues (object[])
  #>
  [CmdletBinding()]
  param(
    [string]$SessionPath,
    [string]$BasePath
  )

  $errors = @()
  $warnings = @()
  $fixableIssues = @()

  $handoffPath = Join-Path $BasePath ".agents/HANDOFF.md"

  if (-not (Test-Path $handoffPath)) {
    return @{
      IsValid = $true
      Errors = $errors
      Warnings = $warnings
      FixableIssues = $fixableIssues
    }
  }

  Push-Location $BasePath
  try {
    $canUseGitDiff = $false
    $gitDiffWorked = $false

    $gitCheck = git rev-parse --git-dir 2>&1
    if ($LASTEXITCODE -eq 0) {
      $originCheck = git rev-parse --verify origin/main 2>&1
      if ($LASTEXITCODE -eq 0) {
        $canUseGitDiff = $true
      }
    }

    if ($canUseGitDiff) {
      $gitDiff = git diff --name-only origin/main...HEAD 2>&1
      if ($LASTEXITCODE -eq 0) {
        $gitDiffWorked = $true
        if ($gitDiff -contains ".agents/HANDOFF.md") {
          $errors += "HANDOFF.md was modified in this branch (detected via git diff). Per SESSION-PROTOCOL.md, agents MUST NOT update HANDOFF.md. Use session log and Serena memory instead."
        }
      } else {
        $warnings += "Git diff failed: $gitDiff. Falling back to timestamp comparison (less reliable in CI)."
      }
    }

    $gitDirCheck = git rev-parse --git-dir 2>&1
    $isGitRepo = $LASTEXITCODE -eq 0
    if ($isGitRepo -and -not $canUseGitDiff) {
      $errors += "Cannot validate HANDOFF.md modification in shallow git checkout. Git diff requires origin/main reference. Ensure full clone or fetch origin/main before validation."
      return @{ IsValid = ($errors.Count -eq 0); Errors = $errors; Warnings = $warnings; FixableIssues = $fixableIssues }
    }

    if (-not $gitDiffWorked) {
      $warnings += 'HANDOFF.md validation using filesystem timestamp (git not available or diff failed). Results may be unreliable in CI environments.'
      $sessionFileName = Split-Path -Leaf $SessionPath
      if ($sessionFileName -match '^(\d{4}-\d{2}-\d{2})') {
        try {
          $sessionDate = [DateTime]::ParseExact($Matches[1], 'yyyy-MM-dd', $null)

          try {
            $handoffItem = Get-Item -LiteralPath $handoffPath -ErrorAction Stop
            $handoffModifiedDate = $handoffItem.LastWriteTime.Date

            if ($handoffModifiedDate -ge $sessionDate) {
              $errors += "HANDOFF.md was modified ($($handoffModifiedDate.ToString('yyyy-MM-dd'))) on or after session date ($($sessionDate.ToString('yyyy-MM-dd'))). Per SESSION-PROTOCOL.md, agents MUST NOT update HANDOFF.md. Use session log and Serena memory instead."
            }
          } catch [System.UnauthorizedAccessException] {
            $errors += 'Permission denied reading HANDOFF.md metadata. Cannot verify modification timestamp. Check file permissions and retry validation.'
            return @{ IsValid = ($errors.Count -eq 0); Errors = $errors; Warnings = $warnings; FixableIssues = $fixableIssues }
          } catch [System.IO.FileNotFoundException] {
            $errors += 'HANDOFF.md was deleted during validation (race condition detected between existence check and metadata read). File system may be unstable. Retry validation. If issue persists, check for concurrent processes or file system issues.'
            return @{ IsValid = ($errors.Count -eq 0); Errors = $errors; Warnings = $warnings; FixableIssues = $fixableIssues }
          } catch [System.IO.PathTooLongException] {
            $errors += 'HANDOFF.md path exceeds maximum length. This indicates a project structure issue. Move project to shorter path.'
            return @{ IsValid = ($errors.Count -eq 0); Errors = $errors; Warnings = $warnings; FixableIssues = $fixableIssues }
          } catch [System.IO.IOException] {
            $errors += "I/O error reading HANDOFF.md: $($_.Exception.Message). Check disk health, file locks, and retry."
            return @{ IsValid = ($errors.Count -eq 0); Errors = $errors; Warnings = $warnings; FixableIssues = $fixableIssues }
          } catch {
            $errors += "Unexpected error reading HANDOFF.md: $($_.Exception.GetType().Name) - $($_.Exception.Message). Contact support if issue persists."
            return @{ IsValid = ($errors.Count -eq 0); Errors = $errors; Warnings = $warnings; FixableIssues = $fixableIssues }
          }
        } catch [System.FormatException] {
          if ($gitDiffWorked) {
            $warnings += "Session log filename has invalid date format: '$($Matches[1])'. Expected format: YYYY-MM-DD (e.g., 2026-01-05). Git validation succeeded but filename should be corrected to match naming convention."
            return @{ IsValid = ($errors.Count -eq 0); Errors = $errors; Warnings = $warnings; FixableIssues = $fixableIssues }
          }

          $errors += "Session log filename contains invalid date format: '$($Matches[1])'. Expected format: YYYY-MM-DD. Cannot validate HANDOFF.md modification without git diff or valid timestamp."
          return @{ IsValid = ($errors.Count -eq 0); Errors = $errors; Warnings = $warnings; FixableIssues = $fixableIssues }
        } catch {
          if ($gitDiffWorked) {
            return @{ IsValid = ($errors.Count -eq 0); Errors = $errors; Warnings = $warnings; FixableIssues = $fixableIssues }
          }

          $errors += "Unexpected error parsing session date: $($_.Exception.GetType().Name) - $($_.Exception.Message). Cannot validate HANDOFF.md modification without git diff or valid timestamp."
          return @{ IsValid = ($errors.Count -eq 0); Errors = $errors; Warnings = $warnings; FixableIssues = $fixableIssues }
        }
      }
    }
  }
  finally {
    Pop-Location
  }
  return @{ IsValid = ($errors.Count -eq 0); Errors = $errors; Warnings = $warnings; FixableIssues = $fixableIssues }
}

function Test-ShouldRequirements {
  <#
  .SYNOPSIS
    Validates SHOULD requirements (warnings only).

  .OUTPUTS
    Hashtable with keys: IsValid (bool), Errors (string[]), Warnings (string[]), FixableIssues (object[])
  #>
  [CmdletBinding()]
  param([string]$Content)

  $totalShould = 0
  $completedShould = 0
  $incompleteShould = @()
  $errors = @()
  $warnings = @()
  $fixableIssues = @()

  $shouldMatches = [regex]::Matches($Content, '\|\s*\*?\*?SHOULD\*?\*?\s*\|([^|]+)\|\s*\[([x ])\]')

  foreach ($match in $shouldMatches) {
    $totalShould++
    $description = $match.Groups[1].Value.Trim()
    $isComplete = $match.Groups[2].Value -eq 'x'

    if ($isComplete) {
      $completedShould++
    } else {
      $incompleteShould += $description
    }
  }

  if ($incompleteShould.Count -gt 0) {
    $warnings += "Incomplete SHOULD requirements: $($incompleteShould.Count)/$totalShould"
  }

  return @{
    IsValid = ($errors.Count -eq 0)
    Errors = $errors
    Warnings = $warnings
    FixableIssues = $fixableIssues
  }
}

function Test-GitCommitEvidence {
  <#
  .SYNOPSIS
    Validates that session log contains commit evidence.

  .OUTPUTS
    Hashtable with keys: IsValid (bool), Errors (string[]), Warnings (string[]), FixableIssues (object[])
  #>
  [CmdletBinding()]
  param([string]$Content)

  $errors = @()
  $warnings = @()
  $fixableIssues = @()

  $commitCandidate = $null
  $commitSectionMatch = [regex]::Match($Content, '(?im)^\s*commit\s*[:\-]?\s*([^\s]+)')
  if ($commitSectionMatch.Success) {
    $commitCandidate = $commitSectionMatch.Groups[1].Value.Trim()
  } else {
    $shaMatch = [regex]::Match($Content, '[0-9a-f]{7,40}')
    if ($shaMatch.Success) {
      $commitCandidate = $shaMatch.Value
    }
  }

  if (-not $commitCandidate) {
    $errors += 'No commit evidence found in session log'
    return @{
      IsValid = $false
      Errors = $errors
      Warnings = $warnings
      FixableIssues = $fixableIssues
    }
  }

  $shaResult = Test-CommitSHAFormat -CommitSHA $commitCandidate
  if (-not $shaResult.IsValid) {
    $errors += $shaResult.Errors
  }

  return @{
    IsValid = ($errors.Count -eq 0)
    Errors = $errors
    Warnings = $warnings
    FixableIssues = $fixableIssues
  }
}

function Test-SessionLogCompleteness {
  <#
  .SYNOPSIS
    Validates that session log has all expected sections.

  .OUTPUTS
    Hashtable with keys: IsValid (bool), Errors (string[]), Warnings (string[]), FixableIssues (object[])
  #>
  [CmdletBinding()]
  param([string]$Content)

  $errors = @()
  $warnings = @()
  $fixableIssues = @()

  $missingSet = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)

  $expectedSections = @(
    @{ Pattern = '(?i)##+\s*Session\s+Info'; Name = 'Session Info' }
    @{ Pattern = '(?i)##+\s*Protocol\s+Compliance'; Name = 'Protocol Compliance' }
    @{ Pattern = '(?i)(##+\s*Work\s+Log|##+\s*Tasks?\s+Completed)'; Name = 'Work Log' }
    @{ Pattern = '(?i)(##+\s*Session\s+End|Session\s+End.*COMPLETE)'; Name = 'Session End' }
    @{ Pattern = '(?i)##+\s*Session\s+Start'; Name = 'Session Start' }
    @{ Pattern = '(?i)##+\s*Evidence'; Name = 'Evidence' }
  )

  foreach ($section in $expectedSections) {
    if (-not ($Content -match $section.Pattern)) {
      [void]$missingSet.Add($section.Name)
    }
  }

  $missing = @($missingSet)
  if ($missing.Count -gt 0) {
    foreach ($item in $missing) {
      $errors += "Missing section: $item"
    }
  }

  $requiredCheck = Test-RequiredSections -SessionLogContent $Content
  if (-not $requiredCheck.IsValid -and $requiredCheck.Errors) {
    $errors += $requiredCheck.Errors
  }

  return @{
    IsValid = ($errors.Count -eq 0)
    Errors = $errors
    Warnings = $warnings
    FixableIssues = $fixableIssues
  }
}

#endregion

function Test-TemplateStructure {
  <#
  .SYNOPSIS
    Checkpoint 1: validates template structure for required sections and tables.

  .OUTPUTS
    Hashtable with keys: IsValid (bool), Errors (string[]), Warnings (string[]), FixableIssues (object[])
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
    Errors = $errors
    Warnings = $warnings
    FixableIssues = @()
  }
}

function Test-EvidenceFields {
  <#
  .SYNOPSIS
    Checkpoint 2: validates evidence fields and path normalization.

  .OUTPUTS
    Hashtable with keys: IsValid (bool), Errors (string[]), Warnings (string[]), FixableIssues (object[])
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
      Errors = $errors
      Warnings = $warnings
      FixableIssues = $fixableIssues
    }
  }

  $evidenceContent = $evidenceMatch.Value

  $pathResult = Test-PathNormalization -SessionLogContent $evidenceContent
  if (-not $pathResult.IsValid) {
    $errors += $pathResult.Errors
    $fixableIssues += $pathResult.FixableIssues
  }

  $commitMatch = [regex]::Match($evidenceContent, 'Commit:\s*([^\s\n]+)')
  if ($commitMatch.Success) {
    $commitSHA = $commitMatch.Groups[1].Value
    $shaResult = Test-CommitSHAFormat -CommitSHA $commitSHA
    if (-not $shaResult.IsValid) {
      $errors += $shaResult.Errors
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
    $warnings += $populationResult.Warnings
    $fixableIssues += $populationResult.FixableIssues
  }

  return @{
    IsValid = ($errors.Count -eq 0)
    Errors = $errors
    Warnings = $warnings
    FixableIssues = $fixableIssues
  }
}

function Invoke-FullValidation {
  <#
  .SYNOPSIS
    Checkpoint 3: executes full validation script.

  .OUTPUTS
    Hashtable with keys: IsValid (bool), Errors (string[]), Warnings (string[]), FixableIssues (object[])
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
      Errors = @("Validation script not found: $validationScript")
      Warnings = @()
      FixableIssues = @()
    }
  }

  try {
    $global:LASTEXITCODE = 0
    $output = & $validationScript -SessionPath $SessionLogPath -Format markdown 2>&1
    $exitCode = if ($null -ne $LASTEXITCODE) { $LASTEXITCODE } else { 0 }

    $errors = $output | Where-Object { $_ -match 'ERROR|FAIL' } | ForEach-Object { $_.ToString() }
    $hasErrors = ($null -ne $errors) -and $errors.Count -gt 0

    if (($exitCode -eq 0 -or $null -eq $exitCode) -and -not $hasErrors) {
      return @{
        IsValid = $true
        Errors = @()
        Warnings = @()
        FixableIssues = @()
      }
    }

    return @{
      IsValid = $false
      Errors = if ($errors) { $errors } else { @('Validation script reported failure with no ERROR/FAIL output.') }
      Warnings = @()
      FixableIssues = @()
    }
  } catch {
    return @{
      IsValid = $false
      Errors = @("Validation script execution failed: $($_.Exception.Message)")
      Warnings = @()
      FixableIssues = @()
    }
  }
}

# Export all functions
Export-ModuleMember -Function `
  Split-TableRow, `
  Parse-ChecklistTable, `
  Normalize-Step, `
  Test-MemoryEvidence, `
  Test-RequiredSections, `
  Test-TableStructure, `
  Test-PathNormalization, `
  Test-CommitSHAFormat, `
  Test-EvidencePopulation, `
  Test-SessionLogExists, `
  Test-ProtocolComplianceSection, `
  Test-MustRequirements, `
  Test-MustNotRequirements, `
  Test-HandoffUpdated, `
  Test-ShouldRequirements, `
  Test-GitCommitEvidence, `
  Test-SessionLogCompleteness, `
  Test-TemplateStructure, `
  Test-EvidenceFields, `
  Invoke-FullValidation
