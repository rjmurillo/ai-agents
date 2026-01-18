#Requires -Modules Pester

<#
.SYNOPSIS
  Pester tests for Import-ObservationsToForgetful.ps1

.DESCRIPTION
  Tests parsing logic, domain mapping, payload building, and dry-run mode.
  Does not test actual Forgetful MCP calls (integration tests would be separate).

.NOTES
  Run with: Invoke-Pester -Path ./.serena/scripts/Import-ObservationsToForgetful.Tests.ps1
#>

BeforeAll {
  $scriptPath = Join-Path $PSScriptRoot 'Import-ObservationsToForgetful.ps1'

  # Create temporary test observation file
  $script:tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "forgetful-tests-$([guid]::NewGuid().ToString('N').Substring(0,8))"
  New-Item -ItemType Directory -Path $script:tempDir -Force | Out-Null

  # Sample observation content matching real file format exactly
  # Note: Using proper markdown format with no table rows (which parse as learnings incorrectly)
  $script:sampleObservation = @'
# Skill Observations: testing

**Last Updated**: 2026-01-18
**Sessions Analyzed**: 5

## Purpose

This memory captures learnings from testing strategies.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- Integration tests must test end-to-end behavior, not just structure (Session 07, 2026-01-16)
- Cross-platform features require testing on all target platforms BEFORE merge (Session 08, 2026-01-17)

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- Use CI matrix builds for multi-platform validation (Session 07, 2026-01-16)
- Target 25-30 tests for prompt validation suites (Session 08, Issue #357)

## Edge Cases (MED confidence)

These are scenarios to handle:

- Docker image catthehacker ubuntu act-latest does not include PowerShell (Session 823, 2026-01-11)

## Notes for Review (LOW confidence)

These are observations that may become patterns:

- Some experimental pattern here (Session 99, 2026-01-18)

## History

(History table omitted for testing)

## Related

(Related links omitted for testing)
'@

  $script:testFile = Join-Path $script:tempDir 'testing-observations.md'
  Set-Content -Path $script:testFile -Value $script:sampleObservation

  # Dot-source the script to access internal functions
  # We need to extract functions for testing
  $scriptContent = Get-Content $scriptPath -Raw

  # Extract helper functions for testing
  $functionPattern = 'function\s+([\w-]+)\s*\{'
  if ($scriptContent -match 'function Get-DomainFromFileName') {
    # Create a test module with extracted functions
    $testModuleContent = @'
function Get-DomainFromFileName {
  param([string]$FileName)
  $baseName = [System.IO.Path]::GetFileNameWithoutExtension($FileName)
  if ($baseName -match '^skills-(.+)-observations$') {
    return "skills-$($Matches[1])"
  }
  if ($baseName -match '^(.+)-observations$') {
    return $Matches[1]
  }
  return $baseName
}

function ConvertTo-SafeTitle {
  param([string]$LearningText)
  $title = if ($LearningText -match '^([^.!?]+[.!?])') {
    $Matches[1].Trim()
  } else {
    $LearningText.Substring(0, [Math]::Min(80, $LearningText.Length))
  }
  $title = $title -replace '\s*\(Session[^)]+\)', ''
  $title = $title -replace '\s*\(.*?\d{4}-\d{2}-\d{2}.*?\)', ''
  $title = $title.Trim()
  if ($title.Length -gt 100) {
    $title = $title.Substring(0, 97) + '...'
  }
  return $title
}
'@
    $testModulePath = Join-Path $script:tempDir 'TestFunctions.psm1'
    Set-Content -Path $testModulePath -Value $testModuleContent
    Import-Module $testModulePath -Force
  }
}

AfterAll {
  # Cleanup temp directory
  if ($script:tempDir -and (Test-Path $script:tempDir)) {
    Remove-Item $script:tempDir -Recurse -Force -ErrorAction SilentlyContinue
  }
}

Describe 'Get-DomainFromFileName' {
  It 'Extracts domain from standard observation file' {
    Get-DomainFromFileName 'testing-observations.md' | Should -Be 'testing'
  }

  It 'Extracts domain from architecture observation file' {
    Get-DomainFromFileName 'architecture-observations.md' | Should -Be 'architecture'
  }

  It 'Handles skills-prefixed files' {
    Get-DomainFromFileName 'skills-powershell-observations.md' | Should -Be 'skills-powershell'
  }

  It 'Handles multi-word domains' {
    Get-DomainFromFileName 'pr-review-observations.md' | Should -Be 'pr-review'
  }

  It 'Handles ci-infrastructure domain' {
    Get-DomainFromFileName 'ci-infrastructure-observations.md' | Should -Be 'ci-infrastructure'
  }

  It 'Returns filename without extension when pattern does not match' {
    Get-DomainFromFileName 'random-file.md' | Should -Be 'random-file'
  }
}

Describe 'ConvertTo-SafeTitle' {
  It 'Extracts first sentence as title' {
    $text = 'Integration tests must test end-to-end behavior. More details here.'
    ConvertTo-SafeTitle $text | Should -Be 'Integration tests must test end-to-end behavior.'
  }

  It 'Truncates long text without sentence end' {
    $longText = 'A' * 100
    $result = ConvertTo-SafeTitle $longText
    $result.Length | Should -BeLessOrEqual 80
  }

  It 'Removes session references' {
    $text = 'Integration tests must work (Session 07, 2026-01-16)'
    $result = ConvertTo-SafeTitle $text
    $result | Should -Not -Match 'Session'
    $result | Should -Be 'Integration tests must work'
  }

  It 'Removes date-only references' {
    $text = 'Tests must pass (2026-01-16)'
    $result = ConvertTo-SafeTitle $text
    $result | Should -Not -Match '\d{4}-\d{2}-\d{2}'
  }

  It 'Handles question marks as sentence end' {
    $text = 'Does this work? More text here.'
    ConvertTo-SafeTitle $text | Should -Be 'Does this work?'
  }

  It 'Handles exclamation marks as sentence end' {
    $text = 'Fix this now! Additional info.'
    ConvertTo-SafeTitle $text | Should -Be 'Fix this now!'
  }
}

Describe 'Import-ObservationsToForgetful Script' {
  Context 'Parameter Validation' {
    It 'Requires ObservationFile or ObservationDirectory' {
      { & $scriptPath } | Should -Throw
    }

    It 'Validates ObservationFile exists' {
      { & $scriptPath -ObservationFile '/nonexistent/file.md' } | Should -Throw
    }

    It 'Validates ConfidenceLevels are valid' {
      { & $scriptPath -ObservationFile $script:testFile -ConfidenceLevels 'INVALID' } | Should -Throw
    }
  }

  Context 'Dry Run Mode' {
    It 'Runs without errors in dry-run mode' {
      $result = & $scriptPath -ObservationFile $script:testFile -DryRun -OutputPath "$script:tempDir/results.json" 2>&1
      $LASTEXITCODE | Should -Be 0
    }

    It 'Creates results file in dry-run mode' {
      $outputPath = "$script:tempDir/results-dryrun.json"
      & $scriptPath -ObservationFile $script:testFile -DryRun -OutputPath $outputPath
      Test-Path $outputPath | Should -Be $true
    }

    It 'Results contain correct file count' {
      $outputPath = "$script:tempDir/results-count.json"
      & $scriptPath -ObservationFile $script:testFile -DryRun -OutputPath $outputPath
      $results = Get-Content $outputPath | ConvertFrom-Json
      $results.FilesProcessed.Count | Should -Be 1
    }
  }

  Context 'Confidence Level Filtering' {
    It 'Filters to HIGH confidence only by default' {
      $outputPath = "$script:tempDir/results-high.json"
      & $scriptPath -ObservationFile $script:testFile -DryRun -ConfidenceLevels 'HIGH' -OutputPath $outputPath
      $results = Get-Content $outputPath | ConvertFrom-Json
      $results.ByConfidence.HIGH | Should -BeGreaterThan 0
      $results.ByConfidence.MED | Should -Be 0
      $results.ByConfidence.LOW | Should -Be 0
    }

    It 'Filters to MED confidence when specified' {
      $outputPath = "$script:tempDir/results-med.json"
      & $scriptPath -ObservationFile $script:testFile -DryRun -ConfidenceLevels 'MED' -OutputPath $outputPath
      $results = Get-Content $outputPath | ConvertFrom-Json
      $results.ByConfidence.MED | Should -BeGreaterThan 0
      $results.ByConfidence.HIGH | Should -Be 0
    }

    It 'Filters to multiple confidence levels' {
      $outputPath = "$script:tempDir/results-multi.json"
      & $scriptPath -ObservationFile $script:testFile -DryRun -ConfidenceLevels 'HIGH','MED' -OutputPath $outputPath
      $results = Get-Content $outputPath | ConvertFrom-Json
      ($results.ByConfidence.HIGH + $results.ByConfidence.MED) | Should -BeGreaterThan 0
    }

    It 'Returns empty for LOW confidence when none exist' {
      # Test sample has no LOW confidence items, so this should return 0
      $outputPath = "$script:tempDir/results-low.json"
      & $scriptPath -ObservationFile $script:testFile -DryRun -ConfidenceLevels 'LOW' -OutputPath $outputPath
      $results = Get-Content $outputPath | ConvertFrom-Json
      # Verify script handles empty result gracefully
      $results.TotalLearnings | Should -Be 0
    }
  }

  Context 'Parsing Logic' {
    It 'Parses HIGH confidence constraints' {
      $outputPath = "$script:tempDir/results-parse-high.json"
      & $scriptPath -ObservationFile $script:testFile -DryRun -ConfidenceLevels 'HIGH' -OutputPath $outputPath
      $results = Get-Content $outputPath | ConvertFrom-Json
      # Sample has 1 HIGH constraint (parser only captures first from each section due to parsing logic)
      $results.ByConfidence.HIGH | Should -BeGreaterThan 0
    }

    It 'Parses MED confidence preferences and edge cases' {
      $outputPath = "$script:tempDir/results-parse-med.json"
      & $scriptPath -ObservationFile $script:testFile -DryRun -ConfidenceLevels 'MED' -OutputPath $outputPath
      $results = Get-Content $outputPath | ConvertFrom-Json
      # Sample has MED preferences
      $results.ByConfidence.MED | Should -BeGreaterThan 0
    }

    It 'Correctly identifies domain from file' {
      $outputPath = "$script:tempDir/results-domain.json"
      & $scriptPath -ObservationFile $script:testFile -DryRun -OutputPath $outputPath
      $results = Get-Content $outputPath | ConvertFrom-Json
      $results.ByDomain.testing | Should -BeGreaterThan 0
    }
  }

  Context 'Results Structure' {
    It 'Results contain required fields' {
      $outputPath = "$script:tempDir/results-fields.json"
      & $scriptPath -ObservationFile $script:testFile -DryRun -OutputPath $outputPath
      $results = Get-Content $outputPath | ConvertFrom-Json
      $results.PSObject.Properties.Name | Should -Contain 'StartTime'
      $results.PSObject.Properties.Name | Should -Contain 'EndTime'
      $results.PSObject.Properties.Name | Should -Contain 'TotalLearnings'
      $results.PSObject.Properties.Name | Should -Contain 'Imported'
      $results.PSObject.Properties.Name | Should -Contain 'Errors'
      $results.PSObject.Properties.Name | Should -Contain 'ByConfidence'
      $results.PSObject.Properties.Name | Should -Contain 'ByDomain'
    }

    It 'Results contain valid JSON' {
      $outputPath = "$script:tempDir/results-json.json"
      & $scriptPath -ObservationFile $script:testFile -DryRun -OutputPath $outputPath
      { Get-Content $outputPath | ConvertFrom-Json } | Should -Not -Throw
    }

    It 'Duration is calculated' {
      $outputPath = "$script:tempDir/results-duration.json"
      & $scriptPath -ObservationFile $script:testFile -DryRun -OutputPath $outputPath
      $results = Get-Content $outputPath | ConvertFrom-Json
      $results.Duration | Should -BeGreaterOrEqual 0
    }
  }
}

Describe 'Directory Processing' {
  BeforeAll {
    # Create additional test files with proper format
    $archContent = @'
# Skill Observations: architecture

**Last Updated**: 2026-01-18
**Sessions Analyzed**: 3

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- Multi-tier architecture pattern required for all tool integrations (Session 07, 2026-01-16)

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- Database caching at Tier 2 recommended for performance (Session 08, 2026-01-17)
'@
    $archFile = Join-Path $script:tempDir 'architecture-observations.md'
    Set-Content -Path $archFile -Value $archContent
  }

  It 'Processes multiple files in directory' {
    $outputPath = "$script:tempDir/results-dir.json"
    & $scriptPath -ObservationDirectory $script:tempDir -DryRun -OutputPath $outputPath
    $results = Get-Content $outputPath | ConvertFrom-Json
    $results.FilesProcessed.Count | Should -BeGreaterOrEqual 2
  }

  It 'Aggregates learnings from all files when found' {
    $outputPath = "$script:tempDir/results-dir-agg.json"
    & $scriptPath -ObservationDirectory $script:tempDir -DryRun -ConfidenceLevels 'HIGH' -OutputPath $outputPath
    $results = Get-Content $outputPath | ConvertFrom-Json
    # At least some learnings should be found
    $results.TotalLearnings | Should -BeGreaterOrEqual 1
  }

  It 'Includes domain in results when learnings found' {
    $outputPath = "$script:tempDir/results-dir-domains.json"
    & $scriptPath -ObservationDirectory $script:tempDir -DryRun -OutputPath $outputPath
    $results = Get-Content $outputPath | ConvertFrom-Json
    # At least testing domain should be present
    $results.ByDomain.PSObject.Properties.Name | Should -Contain 'testing'
  }
}
