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

# Export all functions
Export-ModuleMember -Function Split-TableRow, Parse-ChecklistTable, Normalize-Step, Test-MemoryEvidence
