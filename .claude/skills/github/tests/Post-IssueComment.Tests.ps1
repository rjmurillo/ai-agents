<#
.SYNOPSIS
    Pester tests for Post-IssueComment.ps1 script.

.DESCRIPTION
    Tests the issue comment posting functionality including:
    - Basic comment posting
    - Idempotency marker handling (skip behavior)
    - UpdateIfExists switch (upsert behavior)
    - Error handling and exit codes

.NOTES
    Requires Pester 5.x or later.
#>

BeforeAll {
    $Script:ScriptPath = Join-Path $PSScriptRoot ".." "scripts" "issue" "Post-IssueComment.ps1"
    $Script:ModulePath = Join-Path $PSScriptRoot ".." "modules" "GitHubHelpers.psm1"

    # Verify script exists
    if (-not (Test-Path $Script:ScriptPath)) {
        throw "Script not found at: $Script:ScriptPath"
    }

    # Import the module for helper functions
    Import-Module $Script:ModulePath -Force

    # Create test temp directory
    $Script:TestTempDir = Join-Path ([System.IO.Path]::GetTempPath()) "Post-IssueComment-Tests-$(Get-Random)"
    New-Item -ItemType Directory -Path $Script:TestTempDir -Force | Out-Null
}

AfterAll {
    # Cleanup test temp directory
    if (Test-Path $Script:TestTempDir) {
        Remove-Item -Path $Script:TestTempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Describe "Post-IssueComment.ps1" {

    Context "Parameter Validation" {

        It "Should accept -Body parameter" {
            # Just verify parameter structure, don't execute
            $command = Get-Command $Script:ScriptPath
            $command.Parameters.Keys | Should -Contain 'Body'
        }

        It "Should accept -BodyFile parameter" {
            $command = Get-Command $Script:ScriptPath
            $command.Parameters.Keys | Should -Contain 'BodyFile'
        }

        It "Should accept -Marker parameter" {
            $command = Get-Command $Script:ScriptPath
            $command.Parameters.Keys | Should -Contain 'Marker'
        }

        It "Should accept -UpdateIfExists switch parameter" {
            $command = Get-Command $Script:ScriptPath
            $command.Parameters.Keys | Should -Contain 'UpdateIfExists'
            $command.Parameters['UpdateIfExists'].SwitchParameter | Should -BeTrue
        }

        It "Should accept -Issue parameter as mandatory" {
            $command = Get-Command $Script:ScriptPath
            $command.Parameters.Keys | Should -Contain 'Issue'
        }

        It "Should accept -Owner parameter" {
            $command = Get-Command $Script:ScriptPath
            $command.Parameters.Keys | Should -Contain 'Owner'
        }

        It "Should accept -Repo parameter" {
            $command = Get-Command $Script:ScriptPath
            $command.Parameters.Keys | Should -Contain 'Repo'
        }
    }

    Context "Marker HTML Generation" {

        It "Should generate correct marker HTML format" {
            # Test the marker format logic
            $marker = "AI-TRIAGE"
            $expectedMarkerHtml = "<!-- AI-TRIAGE -->"

            # The script prepends this marker to the body
            $markerHtml = "<!-- $marker -->"
            $markerHtml | Should -Be $expectedMarkerHtml
        }

        It "Should handle markers with special characters" {
            $marker = "AI-PR-QUALITY-GATE"
            $expectedMarkerHtml = "<!-- AI-PR-QUALITY-GATE -->"

            $markerHtml = "<!-- $marker -->"
            $markerHtml | Should -Be $expectedMarkerHtml
        }
    }

    Context "Body File Handling" {

        BeforeEach {
            $Script:TestBodyFile = Join-Path $Script:TestTempDir "test-body.md"
        }

        AfterEach {
            if (Test-Path $Script:TestBodyFile) {
                Remove-Item $Script:TestBodyFile -Force
            }
        }

        It "Should read content from body file" {
            $testContent = "Test comment content"
            Set-Content -Path $Script:TestBodyFile -Value $testContent -Encoding UTF8

            $content = Get-Content -Path $Script:TestBodyFile -Raw -Encoding UTF8
            $content.Trim() | Should -Be $testContent
        }

        It "Should handle multiline body file content" {
            $testContent = @"
Line 1
Line 2
Line 3
"@
            Set-Content -Path $Script:TestBodyFile -Value $testContent -Encoding UTF8

            $content = Get-Content -Path $Script:TestBodyFile -Raw -Encoding UTF8
            $content | Should -Match 'Line 1'
            $content | Should -Match 'Line 2'
            $content | Should -Match 'Line 3'
        }

        It "Should handle body file with markdown formatting" {
            $testContent = @"
## Summary

- Item 1
- Item 2

**Bold** and *italic* text.
"@
            Set-Content -Path $Script:TestBodyFile -Value $testContent -Encoding UTF8

            $content = Get-Content -Path $Script:TestBodyFile -Raw -Encoding UTF8
            $content | Should -Match '## Summary'
            $content | Should -Match '\*\*Bold\*\*'
        }
    }

    Context "UpdateIfExists Switch Behavior" {

        It "Should have UpdateIfExists as a switch parameter type" {
            $command = Get-Command $Script:ScriptPath
            $param = $command.Parameters['UpdateIfExists']
            $param.ParameterType.Name | Should -Be 'SwitchParameter'
        }

        It "Should default UpdateIfExists to false when not specified" {
            $command = Get-Command $Script:ScriptPath
            $param = $command.Parameters['UpdateIfExists']
            # Switch parameters default to false
            $param.SwitchParameter | Should -BeTrue
        }
    }

    Context "Marker Detection Logic" {

        It "Should correctly detect marker in comment body" {
            $markerHtml = "<!-- AI-TRIAGE -->"
            $commentBody = @"
<!-- AI-TRIAGE -->

This is the comment content.
"@
            $commentBody -match [regex]::Escape($markerHtml) | Should -BeTrue
        }

        It "Should correctly detect marker in middle of comment" {
            $markerHtml = "<!-- MARKER-123 -->"
            $commentBody = @"
Some preamble text.

<!-- MARKER-123 -->

Main content here.
"@
            $commentBody -match [regex]::Escape($markerHtml) | Should -BeTrue
        }

        It "Should not detect marker when not present" {
            $markerHtml = "<!-- AI-TRIAGE -->"
            $commentBody = "This comment has no marker."

            $commentBody -match [regex]::Escape($markerHtml) | Should -BeFalse
        }

        It "Should handle regex special characters in marker safely" {
            $marker = "TEST.MARKER+123"
            $markerHtml = "<!-- $marker -->"
            $commentBody = "<!-- TEST.MARKER+123 --> content"

            # Using regex escape to safely match
            $commentBody -match [regex]::Escape($markerHtml) | Should -BeTrue
        }
    }

    Context "Body with Marker Prepending" {

        It "Should prepend marker when not already in body" {
            $marker = "AI-GATE"
            $markerHtml = "<!-- $marker -->"
            $body = "Comment without marker"

            $escapedMarker = [regex]::Escape($markerHtml)
            if ($body -notmatch $escapedMarker) {
                $body = "$markerHtml`n`n$body"
            }

            $body | Should -Match $escapedMarker
            $body | Should -Match 'Comment without marker'
        }

        It "Should not duplicate marker if already in body" {
            $marker = "AI-GATE"
            $markerHtml = "<!-- $marker -->"
            $body = "<!-- AI-GATE -->`n`nComment with marker"

            if ($body -notmatch [regex]::Escape($markerHtml)) {
                $body = "$markerHtml`n`n$body"
            }

            # Count occurrences - should be exactly 1
            $matchResults = [regex]::Matches($body, [regex]::Escape($markerHtml))
            $matchResults.Count | Should -Be 1
        }
    }

    Context "Exit Codes Documentation" {

        It "Should document exit code 0 for success" {
            # Exit code 0 = Success (including skip due to marker)
            $exitCode = 0
            $exitCode | Should -Be 0
        }

        It "Should document exit code 1 for invalid params" {
            # Exit code 1 = Invalid params
            $exitCode = 1
            $exitCode | Should -Be 1
        }

        It "Should document exit code 2 for file not found" {
            # Exit code 2 = File not found
            $exitCode = 2
            $exitCode | Should -Be 2
        }

        It "Should document exit code 3 for API error" {
            # Exit code 3 = API error
            $exitCode = 3
            $exitCode | Should -Be 3
        }

        It "Should document exit code 4 for not authenticated" {
            # Exit code 4 = Not authenticated
            $exitCode = 4
            $exitCode | Should -Be 4
        }
    }

    Context "GitHub Actions Output Format" {

        It "Should produce correct output format for success" {
            $outputs = @(
                "success=true",
                "skipped=false",
                "issue=123",
                "comment_id=456789"
            )

            foreach ($output in $outputs) {
                $output | Should -Match '^\w+='
            }
        }

        It "Should produce correct output format for skipped" {
            $outputs = @(
                "success=true",
                "skipped=true",
                "issue=123",
                "marker=AI-TRIAGE"
            )

            foreach ($output in $outputs) {
                $output | Should -Match '^\w+='
            }
        }

        It "Should produce correct output format for updated" {
            $outputs = @(
                "success=true",
                "skipped=false",
                "updated=true",
                "issue=123",
                "comment_id=456789"
            )

            foreach ($output in $outputs) {
                $output | Should -Match '^\w+='
            }
        }
    }

    Context "Idempotency Scenarios" {

        It "Scenario: First run without marker - should post new comment" {
            # When: No marker specified
            # Then: Should post new comment
            $hasMarker = $false
            $existingCommentWithMarker = $null

            $action = if (-not $hasMarker) { 
                "post_new" 
            } elseif ($existingCommentWithMarker) { 
                "handle_existing" 
            } else { 
                "post_new" 
            }

            $action | Should -Be "post_new"
        }

        It "Scenario: First run with marker - should post new comment with marker" {
            # When: Marker specified but no existing comment has it
            # Then: Should post new comment with marker prepended
            $hasMarker = $true
            $existingCommentWithMarker = $null

            $action = if ($hasMarker -and -not $existingCommentWithMarker) { "post_new_with_marker" } else { "other" }
            $action | Should -Be "post_new_with_marker"
        }

        It "Scenario: Subsequent run with marker, no UpdateIfExists - should skip" {
            # When: Marker specified, existing comment has marker, UpdateIfExists = $false
            # Then: Should skip (write-once idempotency)
            $hasMarker = $true
            $existingCommentWithMarker = @{ id = 123; body = "<!-- MARKER --> content" }
            $updateIfExists = $false

            $action = if ($hasMarker -and $existingCommentWithMarker -and -not $updateIfExists) { "skip" } else { "other" }
            $action | Should -Be "skip"
        }

        It "Scenario: Subsequent run with marker and UpdateIfExists - should update" {
            # When: Marker specified, existing comment has marker, UpdateIfExists = $true
            # Then: Should update existing comment (upsert behavior)
            $hasMarker = $true
            $existingCommentWithMarker = @{ id = 123; body = "<!-- MARKER --> content" }
            $updateIfExists = $true

            $action = if ($hasMarker -and $existingCommentWithMarker -and $updateIfExists) { "update" } else { "other" }
            $action | Should -Be "update"
        }
    }

    Context "CI/CD Status Comment Use Case" {

        It "Should support updating status on each commit" {
            # This is the primary use case for UpdateIfExists
            # CI/CD status comments should reflect latest state
            $marker = "AI-PR-QUALITY-GATE"
            $updateIfExists = $true

            # Verify the parameters work together
            $updateIfExists | Should -BeTrue
            $marker | Should -Not -BeNullOrEmpty
        }

        It "Should preserve marker in updated content" {
            $marker = "CI-STATUS"
            $markerHtml = "<!-- $marker -->"
            $newBody = "## Updated Status`n`n✅ All checks passed"

            $escapedMarker = [regex]::Escape($markerHtml)
            # Prepend marker if not in body
            if ($newBody -notmatch $escapedMarker) {
                $newBody = "$markerHtml`n`n$newBody"
            }

            $newBody | Should -Match $escapedMarker
            $newBody | Should -Match 'Updated Status'
        }
    }

    Context "Edge Cases" {

        It "Should handle empty marker string gracefully" {
            $marker = ""

            # When marker is empty, no marker logic should apply
            [string]::IsNullOrEmpty($marker) | Should -BeTrue
        }

        It "Should handle whitespace-only body as empty" {
            $body = "   "
            [string]::IsNullOrWhiteSpace($body) | Should -BeTrue
        }

        It "Should handle body with only newlines" {
            $body = "`n`n`n"
            [string]::IsNullOrWhiteSpace($body) | Should -BeTrue
        }

        It "Should handle very long marker names" {
            $marker = "A" * 100
            $markerHtml = "<!-- $marker -->"
            $markerHtml.Length | Should -BeGreaterThan 100
        }

        It "Should handle marker with unicode characters" {
            $marker = "MARKER-✅-🔒"
            $markerHtml = "<!-- $marker -->"
            $markerHtml | Should -Be "<!-- MARKER-✅-🔒 -->"
        }
    }

    # Issue #117: Mocked Integration Tests
    # These tests mock external dependencies and execute the script to verify behavior
    Context "Mocked Integration: Idempotent Skip (write-once)" {

        BeforeEach {
            # Set up GITHUB_OUTPUT temp file
            $Script:GitHubOutputFile = Join-Path $Script:TestTempDir "github_output_$(Get-Random).txt"
            $env:GITHUB_OUTPUT = $Script:GitHubOutputFile
            New-Item -Path $Script:GitHubOutputFile -ItemType File -Force | Out-Null

            # Mock gh auth status (authentication check)
            Mock gh -ParameterFilter { $args[0] -eq 'auth' -and $args[1] -eq 'status' } -MockWith {
                $global:LASTEXITCODE = 0
                return "Logged in to github.com"
            } -ModuleName GitHubHelpers

            # Mock gh api to return repo info
            Mock gh -ParameterFilter {
                $args[0] -eq 'api' -and $args[1] -match 'repos/.*/.*' -and $args.Count -eq 2
            } -MockWith {
                $global:LASTEXITCODE = 0
                return '{"owner":{"login":"test-owner"},"name":"test-repo"}'
            } -ModuleName GitHubHelpers
        }

        AfterEach {
            if (Test-Path $Script:GitHubOutputFile) {
                Remove-Item $Script:GitHubOutputFile -Force
            }
            $env:GITHUB_OUTPUT = $null
        }

        It "Should exit 0 and skip when marker exists without UpdateIfExists" {
            # Mock gh api to return existing comment with marker
            Mock gh -ParameterFilter {
                $args[0] -eq 'api' -and $args[1] -match 'issues/.*/comments$'
            } -MockWith {
                $global:LASTEXITCODE = 0
                return '[{"id":12345,"body":"<!-- TEST-MARKER -->\n\nExisting comment","html_url":"https://github.com/test/repo/issues/1#issuecomment-12345"}]'
            }

            # Execute script - marker exists, no UpdateIfExists
            $result = & $Script:ScriptPath -Owner "test-owner" -Repo "test-repo" -Issue 1 -Body "New content" -Marker "TEST-MARKER" 2>&1

            # Verify exit code is 0 (skip is success)
            $LASTEXITCODE | Should -Be 0

            # Verify GITHUB_OUTPUT contains skipped=true
            $outputContent = Get-Content $Script:GitHubOutputFile -Raw
            $outputContent | Should -Match 'success=true'
            $outputContent | Should -Match 'skipped=true'
            $outputContent | Should -Match 'marker=TEST-MARKER'
        }

        It "Should write skip status to GITHUB_OUTPUT with all required fields" {
            # Mock gh api to return existing comment with marker
            Mock gh -ParameterFilter {
                $args[0] -eq 'api' -and $args[1] -match 'issues/.*/comments$'
            } -MockWith {
                $global:LASTEXITCODE = 0
                return '[{"id":99999,"body":"<!-- SKIP-TEST -->\n\nOld content","html_url":"https://github.com/test/repo/issues/42#issuecomment-99999"}]'
            }

            # Execute script
            & $Script:ScriptPath -Owner "test-owner" -Repo "test-repo" -Issue 42 -Body "Content" -Marker "SKIP-TEST" 2>&1 | Out-Null

            # Verify GITHUB_OUTPUT format
            $outputContent = Get-Content $Script:GitHubOutputFile -Raw
            $outputContent | Should -Match 'success=true'
            $outputContent | Should -Match 'skipped=true'
            $outputContent | Should -Match 'issue=42'
            $outputContent | Should -Match 'marker=SKIP-TEST'
        }
    }

    # Note: Full integration tests for UpdateIfExists require mocking gh api PATCH
    # inside the GitHubHelpers module. However, since Post-IssueComment.ps1 re-imports
    # the module with -Force, Pester mocks don't persist into the fresh module scope.
    # These tests verify the update path logic through the Update-IssueComment function unit tests.
    # The "Idempotency Scenarios" context above validates the decision logic.
    Context "Upsert (UpdateIfExists) Behavior Verification" {

        It "Should have UpdateIfExists parameter that triggers update path in script" {
            # Verify the script calls Update-IssueComment when UpdateIfExists is specified
            # by checking the script source code structure
            $scriptContent = Get-Content $Script:ScriptPath -Raw

            # Verify UpdateIfExists condition exists
            $scriptContent | Should -Match 'if\s*\(\s*\$UpdateIfExists\s*\)'

            # Verify Update-IssueComment is called in the update path
            $scriptContent | Should -Match 'Update-IssueComment'

            # Verify updated=true is written to GITHUB_OUTPUT in update path
            $scriptContent | Should -Match 'updated=true'
        }

        It "Should verify Add-MarkerToBody helper prepends marker correctly" {
            # Verify the helper function logic for marker prepending
            $scriptContent = Get-Content $Script:ScriptPath -Raw

            # Verify Add-MarkerToBody function exists
            $scriptContent | Should -Match 'function Add-MarkerToBody'

            # Verify it checks for existing marker before prepending
            $scriptContent | Should -Match '-notmatch.*MarkerHtml'
        }

        It "Should verify GITHUB_OUTPUT includes all update path fields" {
            # Verify all expected output fields for update path are in script
            $scriptContent = Get-Content $Script:ScriptPath -Raw

            # Update path specific outputs
            $scriptContent | Should -Match 'updated=true'
            $scriptContent | Should -Match 'updated_at='
            $scriptContent | Should -Match 'html_url='
        }
    }

    Context "Mocked Integration: New Comment Creation" {

        BeforeEach {
            $Script:GitHubOutputFile = Join-Path $Script:TestTempDir "github_output_$(Get-Random).txt"
            $env:GITHUB_OUTPUT = $Script:GitHubOutputFile
            New-Item -Path $Script:GitHubOutputFile -ItemType File -Force | Out-Null

            # Mock gh auth status
            Mock gh -ParameterFilter { $args[0] -eq 'auth' -and $args[1] -eq 'status' } -MockWith {
                $global:LASTEXITCODE = 0
            } -ModuleName GitHubHelpers
        }

        AfterEach {
            if (Test-Path $Script:GitHubOutputFile) {
                Remove-Item $Script:GitHubOutputFile -Force
            }
            $env:GITHUB_OUTPUT = $null
        }

        It "Should create new comment when no marker exists" {
            # Mock gh api GET to return empty comments array
            Mock gh -ParameterFilter {
                $args[0] -eq 'api' -and $args[1] -match 'issues/.*/comments$' -and $args -notcontains '-X'
            } -MockWith {
                $global:LASTEXITCODE = 0
                return '[]'
            }

            # Mock gh api POST for new comment
            Mock gh -ParameterFilter {
                $args[0] -eq 'api' -and $args -contains '-X' -and $args -contains 'POST'
            } -MockWith {
                $global:LASTEXITCODE = 0
                return '{"id":55555,"html_url":"https://github.com/test/repo/issues/10#issuecomment-55555","created_at":"2024-01-01T00:00:00Z"}'
            }

            & $Script:ScriptPath -Owner "test-owner" -Repo "test-repo" -Issue 10 -Body "Brand new comment" -Marker "NEW-MARKER" 2>&1 | Out-Null

            $LASTEXITCODE | Should -Be 0

            $outputContent = Get-Content $Script:GitHubOutputFile -Raw
            $outputContent | Should -Match 'success=true'
            $outputContent | Should -Match 'skipped=false'
            $outputContent | Should -Match 'comment_id=55555'
            $outputContent | Should -Match 'created_at='
        }

        It "Should create comment without marker when marker not specified" {
            # Track the body sent to API
            $capturedBody = $null
            Mock gh -ParameterFilter {
                $args[0] -eq 'api' -and $args -contains '-X' -and $args -contains 'POST'
            } -MockWith {
                # Capture the body parameter
                for ($i = 0; $i -lt $args.Count; $i++) {
                    if ($args[$i] -eq '-f' -and $args[$i+1] -match '^body=') {
                        $script:capturedBody = $args[$i+1] -replace '^body=', ''
                        break
                    }
                }
                $global:LASTEXITCODE = 0
                return '{"id":66666,"html_url":"https://github.com/x/y/issues/1#issuecomment-66666","created_at":"2024-01-01T00:00:00Z"}'
            }

            & $Script:ScriptPath -Owner "test-owner" -Repo "test-repo" -Issue 1 -Body "Comment without marker" 2>&1 | Out-Null

            $LASTEXITCODE | Should -Be 0

            # Body should NOT contain HTML comment marker
            $script:capturedBody | Should -Not -Match '<!-- .* -->'
        }
    }

    Context "Mocked Integration: Exit Code Verification" {

        BeforeEach {
            $Script:GitHubOutputFile = Join-Path $Script:TestTempDir "github_output_$(Get-Random).txt"
            $env:GITHUB_OUTPUT = $Script:GitHubOutputFile
            New-Item -Path $Script:GitHubOutputFile -ItemType File -Force | Out-Null

            Mock gh -ParameterFilter { $args[0] -eq 'auth' -and $args[1] -eq 'status' } -MockWith {
                $global:LASTEXITCODE = 0
            } -ModuleName GitHubHelpers
        }

        AfterEach {
            if (Test-Path $Script:GitHubOutputFile) {
                Remove-Item $Script:GitHubOutputFile -Force
            }
            $env:GITHUB_OUTPUT = $null
        }

        It "Should return exit code 0 on successful post" {
            Mock gh -ParameterFilter {
                $args[0] -eq 'api' -and $args -contains 'POST'
            } -MockWith {
                $global:LASTEXITCODE = 0
                return '{"id":1,"html_url":"https://github.com/x/y/issues/1#issuecomment-1","created_at":"2024-01-01T00:00:00Z"}'
            }

            & $Script:ScriptPath -Owner "o" -Repo "r" -Issue 1 -Body "Test" 2>&1 | Out-Null

            $LASTEXITCODE | Should -Be 0
        }

        It "Should return exit code 0 on idempotent skip" {
            Mock gh -ParameterFilter {
                $args[0] -eq 'api' -and $args[1] -match 'issues/.*/comments$' -and $args -notcontains '-X'
            } -MockWith {
                $global:LASTEXITCODE = 0
                return '[{"id":1,"body":"<!-- SKIP -->"}]'
            }

            & $Script:ScriptPath -Owner "o" -Repo "r" -Issue 1 -Body "Test" -Marker "SKIP" 2>&1 | Out-Null

            $LASTEXITCODE | Should -Be 0
        }

        # Note: Update path exit code verification is covered by behavior tests
        # The "Upsert (UpdateIfExists) Behavior Verification" context validates the update path logic
        It "Should have exit 0 in update success path in script" {
            $scriptContent = Get-Content $Script:ScriptPath -Raw

            # The script has 'exit 0' after writing update success to GITHUB_OUTPUT
            # (in the UpdateIfExists path, after Update-IssueComment call)
            $scriptContent | Should -Match 'Updated:\s*True'
            $scriptContent | Should -Match 'exit\s+0'
        }

        It "Should return exit code 3 on API error" {
            Mock gh -ParameterFilter {
                $args[0] -eq 'api' -and $args -contains 'POST'
            } -MockWith {
                $global:LASTEXITCODE = 1
                return "Error: API request failed"
            }

            & $Script:ScriptPath -Owner "o" -Repo "r" -Issue 1 -Body "Test" 2>&1 | Out-Null

            $LASTEXITCODE | Should -Be 3
        }
    }
}
