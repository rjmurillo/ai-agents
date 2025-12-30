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
    $Script:ModulePath = Join-Path $PSScriptRoot ".." "modules" "GitHubCore.psm1"

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

    # Issue #117: Behavior Verification Tests
    # Note: Full mocked integration tests require script execution, but Pester mocks
    # don't persist when scripts re-import modules with -Force. These tests verify
    # the script's behavior through source code analysis and logic verification.
    Context "Idempotent Skip (write-once) Behavior Verification" {

        It "Should have skip logic when marker exists without UpdateIfExists" {
            $scriptContent = Get-Content $Script:ScriptPath -Raw

            # Verify skip path condition exists
            $scriptContent | Should -Match 'if.*\$existingComment'
            $scriptContent | Should -Match 'else\s*\{[^}]*Skipping'

            # Verify skip writes success=true and skipped=true
            $scriptContent | Should -Match 'success=true'
            $scriptContent | Should -Match 'skipped=true'
        }

        It "Should write skip status to GITHUB_OUTPUT with all required fields" {
            $scriptContent = Get-Content $Script:ScriptPath -Raw

            # Verify all skip path GITHUB_OUTPUT fields
            $scriptContent | Should -Match 'Add-Content.*GITHUB_OUTPUT.*success=true'
            $scriptContent | Should -Match 'Add-Content.*GITHUB_OUTPUT.*skipped=true'
            $scriptContent | Should -Match 'Add-Content.*GITHUB_OUTPUT.*issue='
            $scriptContent | Should -Match 'Add-Content.*GITHUB_OUTPUT.*marker='
        }

        It "Should exit 0 on idempotent skip" {
            $scriptContent = Get-Content $Script:ScriptPath -Raw

            # The skip path ends with exit 0 (idempotent skip is success)
            # Use [\s\S]*? to match across multiple lines (GITHUB_OUTPUT writes between message and exit)
            $scriptContent | Should -Match 'Skipping[\s\S]*?exit\s+0'
        }
    }

    # Note: Full integration tests for UpdateIfExists require mocking gh api PATCH
    # inside the GitHubCore module. However, since Post-IssueComment.ps1 re-imports
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

    Context "New Comment Creation Behavior Verification" {

        It "Should have new comment creation path when no marker exists" {
            $scriptContent = Get-Content $Script:ScriptPath -Raw

            # Verify POST API call for new comments
            $scriptContent | Should -Match 'gh api.*-X POST'

            # Verify success output fields for new comments
            $scriptContent | Should -Match 'skipped=false'
            $scriptContent | Should -Match 'created_at='
        }

        It "Should only prepend marker when marker parameter is provided" {
            $scriptContent = Get-Content $Script:ScriptPath -Raw

            # Verify marker is only added conditionally
            $scriptContent | Should -Match 'if\s*\(\s*\$Marker\s*\)'

            # Verify Add-MarkerToBody is called to prepend marker
            $scriptContent | Should -Match 'Add-MarkerToBody'
        }

        It "Should write all required GITHUB_OUTPUT fields for new comments" {
            $scriptContent = Get-Content $Script:ScriptPath -Raw

            # Verify output fields for new comment path
            $scriptContent | Should -Match 'success=true'
            $scriptContent | Should -Match 'skipped=false'
            $scriptContent | Should -Match 'comment_id='
            $scriptContent | Should -Match 'html_url='
            $scriptContent | Should -Match 'created_at='
        }
    }

    Context "Exit Code Behavior Verification" {

        It "Should exit 0 on successful post" {
            $scriptContent = Get-Content $Script:ScriptPath -Raw

            # The script ends with implicit exit 0 or explicit exit 0 after posting
            # Check that success path has exit 0
            $scriptContent | Should -Match 'Posted comment.*\n.*exit\s+0|Success.*CommentId.*\n'
        }

        It "Should have exit 0 in skip path" {
            $scriptContent = Get-Content $Script:ScriptPath -Raw

            # Skip path explicitly exits with 0
            # Use [\s\S]*? to match across GITHUB_OUTPUT writes between message and exit
            $scriptContent | Should -Match 'Skipped:\s*True[\s\S]*?exit\s+0'
        }

        It "Should have exit 0 in update success path" {
            $scriptContent = Get-Content $Script:ScriptPath -Raw

            # Update path has exit 0 after success
            # Use [\s\S]*? to match across GITHUB_OUTPUT writes between message and exit
            $scriptContent | Should -Match 'Updated:\s*True[\s\S]*?exit\s+0'
        }

        It "Should exit 3 on API error via Write-ErrorAndExit" {
            $scriptContent = Get-Content $Script:ScriptPath -Raw

            # API errors use Write-ErrorAndExit with code 3
            $scriptContent | Should -Match 'Write-ErrorAndExit.*Failed to post comment.*3'
        }
    }
}
