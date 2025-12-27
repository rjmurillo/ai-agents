#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Invoke-PRCommentProcessing.ps1

.DESCRIPTION
    Tests the PR comment processing script including:
    - Parameter validation
    - JSON parsing and error handling
    - Comment acknowledgment logic
    - Classification-based routing
    - Exit code behavior

.NOTES
    Test Approach:
    1. PATTERN-BASED TESTS: Validate script structure
    2. FUNCTIONAL TESTS: Test extracted functions with mock data
    3. EDGE CASE TESTS: Verify error handling and boundary conditions
#>

BeforeAll {
    $repoRoot = Join-Path $PSScriptRoot ".."
    $scriptPath = Join-Path $repoRoot ".claude" "skills" "github" "scripts" "pr" "Invoke-PRCommentProcessing.ps1"

    # Load script content for pattern-based testing
    $script:scriptContent = Get-Content $scriptPath -Raw
}

Describe "Invoke-PRCommentProcessing Script Structure" {

    Context "Parameter Definitions" {
        It "Has PRNumber as mandatory parameter" {
            $script:scriptContent | Should -Match '\[Parameter\(Mandatory\)\]\s*\[int\]\$PRNumber'
        }

        It "Has Verdict as mandatory parameter" {
            $script:scriptContent | Should -Match '\[Parameter\(Mandatory\)\]\s*\[string\]\$Verdict'
        }

        It "Has FindingsJson as mandatory parameter" {
            $script:scriptContent | Should -Match '\[Parameter\(Mandatory\)\]\s*\[string\]\$FindingsJson'
        }

        It "Has DryRun as optional switch" {
            $script:scriptContent | Should -Match '\[switch\]\$DryRun'
        }
    }

    Context "Module Dependencies" {
        It "Imports GitHubHelpers module" {
            $script:scriptContent | Should -Match 'GitHubHelpers\.psm1'
            $script:scriptContent | Should -Match 'Import-Module'
        }

        It "Uses Resolve-RepoParams from module" {
            $script:scriptContent | Should -Match 'Resolve-RepoParams'
        }
    }

    Context "Exit Codes Documentation" {
        It "Documents exit code 0 for success" {
            $script:scriptContent | Should -Match '0\s*=\s*Success'
        }

        It "Documents exit code 1 for invalid params" {
            $script:scriptContent | Should -Match '1\s*=\s*Invalid'
        }

        It "Documents exit code 2 for parse error" {
            $script:scriptContent | Should -Match '2\s*=\s*Parse'
        }

        It "Documents exit code 3 for API error" {
            $script:scriptContent | Should -Match '3\s*=\s*API'
        }
    }

    Context "Core Functions" {
        It "Has Get-Findings function" {
            $script:scriptContent | Should -Match 'function Get-Findings'
        }

        It "Has Add-CommentReaction function" {
            $script:scriptContent | Should -Match 'function Add-CommentReaction'
        }

        It "Has Invoke-CommentProcessing function" {
            $script:scriptContent | Should -Match 'function Invoke-CommentProcessing'
        }
    }

    Context "Classification Handling" {
        It "Handles stale classification" {
            $script:scriptContent | Should -Match "'stale'\s*\{"
        }

        It "Handles wontfix classification" {
            $script:scriptContent | Should -Match "'wontfix'\s*\{"
        }

        It "Handles question classification" {
            $script:scriptContent | Should -Match "'question'\s*\{"
        }

        It "Handles quick-fix, standard, strategic classifications" {
            $script:scriptContent | Should -Match "'quick-fix'.*'standard'.*'strategic'"
        }
    }

    Context "Verdict Filtering" {
        It "Filters by PASS and WARN verdicts" {
            $script:scriptContent | Should -Match "\`$Verdict\s+-notin\s+'PASS',\s*'WARN'"
        }
    }

    Context "Stats Tracking" {
        It "Tracks Acknowledged count" {
            $script:scriptContent | Should -Match 'Acknowledged\s*='
        }

        It "Tracks Replied count" {
            $script:scriptContent | Should -Match 'Replied\s*='
        }

        It "Tracks Resolved count" {
            $script:scriptContent | Should -Match 'Resolved\s*='
        }

        It "Tracks Skipped count" {
            $script:scriptContent | Should -Match 'Skipped\s*='
        }

        It "Tracks Errors count" {
            $script:scriptContent | Should -Match 'Errors\s*='
        }
    }
}

#region Functional Tests

Describe "Get-Findings Function" {

    BeforeAll {
        # Extract and define the Get-Findings function for testing
        if ($script:scriptContent -match 'function Get-Findings \{[\s\S]*?(?=\n\n# )') {
            $functionDef = $Matches[0]
            Invoke-Expression $functionDef
        }
    }

    Context "Valid JSON Parsing" {
        It "Parses valid JSON without code fences" {
            $json = '{"comments": [{"id": 123, "classification": "quick-fix"}]}'
            $result = Get-Findings -Json $json
            $result | Should -Not -BeNullOrEmpty
            $result.comments.Count | Should -Be 1
            $result.comments[0].id | Should -Be 123
        }

        It "Parses JSON wrapped in code fences" {
            $json = '```json
{"comments": [{"id": 456, "classification": "standard"}]}
```'
            $result = Get-Findings -Json $json
            $result | Should -Not -BeNullOrEmpty
            $result.comments[0].id | Should -Be 456
        }

        It "Parses JSON with just json fence marker" {
            $json = '```json
{"comments": [], "verdict": "PASS"}
```'
            $result = Get-Findings -Json $json
            $result.verdict | Should -Be "PASS"
        }
    }

    Context "Empty and Null Inputs" {
        It "Handles empty comments array" {
            $json = '{"comments": [], "verdict": "PASS"}'
            $result = Get-Findings -Json $json
            $result.comments.Count | Should -Be 0
        }
    }

    Context "Complex JSON Structures" {
        It "Parses complete triage output" {
            $json = @'
{
  "comments": [
    {
      "id": 123456789,
      "author": "gemini-code-assist",
      "file": "src/utils.ps1",
      "line": 42,
      "classification": "quick-fix",
      "priority": "major",
      "action": "implement",
      "summary": "Add null check",
      "resolution": "Add if ($null -ne $obj) guard"
    }
  ],
  "summary": {
    "total": 1,
    "quick_fix": 1
  },
  "verdict": "PASS"
}
'@
            $result = Get-Findings -Json $json
            $result.comments[0].author | Should -Be "gemini-code-assist"
            $result.comments[0].classification | Should -Be "quick-fix"
            $result.comments[0].priority | Should -Be "major"
            $result.summary.total | Should -Be 1
        }
    }
}

Describe "Invoke-CommentProcessing Function" {

    BeforeAll {
        # Mock Add-CommentReaction for testing
        function Add-CommentReaction {
            param([long]$CommentId, [string]$Reaction = 'eyes')
            # Mock implementation - just return success
        }

        # Extract Invoke-CommentProcessing function
        if ($script:scriptContent -match 'function Invoke-CommentProcessing \{[\s\S]*?(?=\n\n# Main)') {
            $functionDef = $Matches[0]
            # Replace the real Add-CommentReaction call with our mock
            Invoke-Expression $functionDef
        }

        # Set DryRun to true for all tests to avoid actual API calls
        $script:DryRun = $true
    }

    Context "Stats Initialization" {
        It "Returns stats object with all required keys" {
            $findings = @{
                comments = @()
            }
            $result = Invoke-CommentProcessing -Findings $findings
            $result.Acknowledged | Should -Be 0
            $result.Replied | Should -Be 0
            $result.Resolved | Should -Be 0
            $result.Skipped | Should -Be 0
            $result.Errors | Should -Be 0
        }
    }

    Context "Classification Routing" {
        It "Increments Resolved for stale classification" {
            $findings = @{
                comments = @(
                    @{ id = 1; classification = 'stale'; summary = 'Old comment' }
                )
            }
            $result = Invoke-CommentProcessing -Findings $findings
            $result.Resolved | Should -Be 1
        }

        It "Increments Skipped for question classification" {
            $findings = @{
                comments = @(
                    @{ id = 2; classification = 'question'; summary = 'Need clarification' }
                )
            }
            $result = Invoke-CommentProcessing -Findings $findings
            $result.Skipped | Should -Be 1
        }

        It "Increments Skipped for quick-fix classification" {
            $findings = @{
                comments = @(
                    @{ id = 3; classification = 'quick-fix'; action = 'implement'; summary = 'Add null check' }
                )
            }
            $result = Invoke-CommentProcessing -Findings $findings
            $result.Skipped | Should -Be 1
        }

        It "Increments Skipped for standard classification" {
            $findings = @{
                comments = @(
                    @{ id = 4; classification = 'standard'; action = 'implement'; summary = 'Refactor' }
                )
            }
            $result = Invoke-CommentProcessing -Findings $findings
            $result.Skipped | Should -Be 1
        }

        It "Increments Skipped for strategic classification" {
            $findings = @{
                comments = @(
                    @{ id = 5; classification = 'strategic'; action = 'reply'; summary = 'Architecture question' }
                )
            }
            $result = Invoke-CommentProcessing -Findings $findings
            $result.Skipped | Should -Be 1
        }
    }

    Context "Multiple Comments" {
        It "Processes multiple comments and aggregates stats" {
            $findings = @{
                comments = @(
                    @{ id = 1; classification = 'stale'; summary = 'Old' }
                    @{ id = 2; classification = 'question'; summary = 'Question' }
                    @{ id = 3; classification = 'quick-fix'; action = 'implement'; summary = 'Fix' }
                )
            }
            $result = Invoke-CommentProcessing -Findings $findings
            $result.Resolved | Should -Be 1
            $result.Skipped | Should -Be 2
            # Acknowledged count depends on successful reaction adds
        }
    }
}

#endregion

#region Edge Case Tests

Describe "Edge Case: Malformed JSON" {

    Context "Invalid JSON Handling" {
        It "Script has try-catch for JSON parsing" {
            $script:scriptContent | Should -Match 'try\s*\{'
            $script:scriptContent | Should -Match 'catch\s*\{'
        }

        It "Script writes error on parse failure" {
            $script:scriptContent | Should -Match 'Write-Error.*Failed to parse'
        }

        It "Script exits with code 2 on parse failure" {
            $script:scriptContent | Should -Match 'exit 2'
        }

        It "Script logs verbose info about raw JSON on error" {
            $script:scriptContent | Should -Match 'Write-Verbose.*Raw JSON'
        }
    }
}

Describe "Edge Case: Verdict Filtering" {

    Context "Non-PASS/WARN Verdicts" {
        It "Script filters non-PASS/WARN verdicts" {
            # The script should exit early (exit 0) for non-PASS/WARN verdicts
            $script:scriptContent | Should -Match '\$Verdict\s+-notin'
        }

        It "Script checks for PASS and WARN" {
            $script:scriptContent | Should -Match "'PASS'.*'WARN'"
        }

        It "Script exits early with warning for invalid verdict" {
            $script:scriptContent | Should -Match 'Write-Warning.*skipping comment processing'
        }
    }
}

Describe "Edge Case: Comment ID Types" {

    Context "Long Comment IDs" {
        It "Script uses [long] type for CommentId parameter" {
            $script:scriptContent | Should -Match '\[long\]\$CommentId'
        }
    }
}

Describe "Edge Case: Empty Findings" {

    BeforeAll {
        # Set DryRun to true
        $script:DryRun = $true

        # Mock Add-CommentReaction
        function Add-CommentReaction {
            param([long]$CommentId, [string]$Reaction = 'eyes')
        }

        if ($script:scriptContent -match 'function Invoke-CommentProcessing \{[\s\S]*?(?=\n\n# Main)') {
            $functionDef = $Matches[0]
            Invoke-Expression $functionDef
        }
    }

    Context "No Comments to Process" {
        It "Handles null comments gracefully" {
            $findings = @{
                comments = $null
            }
            # Should not throw, just return empty stats
            $result = Invoke-CommentProcessing -Findings $findings
            $result.Acknowledged | Should -Be 0
        }

        It "Handles empty comments array" {
            $findings = @{
                comments = @()
            }
            $result = Invoke-CommentProcessing -Findings $findings
            $result.Acknowledged | Should -Be 0
            $result.Skipped | Should -Be 0
        }
    }
}

Describe "Edge Case: DryRun Mode" {

    Context "DryRun Behavior" {
        It "Script has DryRun checks for reactions" {
            $script:scriptContent | Should -Match 'if\s*\(\$DryRun\)'
        }

        It "Script logs DryRun actions" {
            $script:scriptContent | Should -Match '\[DRY-RUN\]'
        }
    }
}

Describe "Edge Case: Wontfix with Missing Resolution" {

    BeforeAll {
        $script:DryRun = $true

        function Add-CommentReaction {
            param([long]$CommentId, [string]$Reaction = 'eyes')
        }

        if ($script:scriptContent -match 'function Invoke-CommentProcessing \{[\s\S]*?(?=\n\n# Main)') {
            $functionDef = $Matches[0]
            Invoke-Expression $functionDef
        }
    }

    Context "Wontfix Classification" {
        It "Does not crash when resolution is null" {
            $findings = @{
                comments = @(
                    @{ id = 1; classification = 'wontfix'; resolution = $null }
                )
            }
            # Should not throw
            { Invoke-CommentProcessing -Findings $findings } | Should -Not -Throw
        }

        It "Does not crash when resolution is empty string" {
            $findings = @{
                comments = @(
                    @{ id = 2; classification = 'wontfix'; resolution = '' }
                )
            }
            { Invoke-CommentProcessing -Findings $findings } | Should -Not -Throw
        }
    }
}

#endregion

#region Integration-Style Tests

Describe "Script Output Format" {

    Context "Summary Output" {
        It "Script outputs processing summary" {
            $script:scriptContent | Should -Match '=== Processing Summary ==='
        }

        It "Script outputs Acknowledged count" {
            $script:scriptContent | Should -Match 'Acknowledged:'
        }

        It "Script outputs Replied count" {
            $script:scriptContent | Should -Match 'Replied:'
        }

        It "Script outputs Resolved count" {
            $script:scriptContent | Should -Match 'Resolved:'
        }

        It "Script outputs Skipped count" {
            $script:scriptContent | Should -Match 'Skipped.*needs human'
        }

        It "Script outputs Errors count" {
            $script:scriptContent | Should -Match 'Errors:'
        }
    }
}

Describe "Error Handling" {

    Context "API Error Handling" {
        It "Script checks LASTEXITCODE after gh api calls" {
            $script:scriptContent | Should -Match '\$LASTEXITCODE\s+-ne\s+0'
        }

        It "Script writes warning on API failure" {
            $script:scriptContent | Should -Match 'Write-Warning.*Failed'
        }

        It "Script exits with code 3 on errors" {
            $script:scriptContent | Should -Match 'exit\s+3'
        }
    }

    Context "Parse Error Handling" {
        It "Script exits with code 2 on parse errors" {
            $script:scriptContent | Should -Match 'exit\s+2'
        }
    }
}

#endregion
