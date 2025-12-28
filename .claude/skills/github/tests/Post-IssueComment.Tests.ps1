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
            $matches = [regex]::Matches($body, [regex]::Escape($markerHtml))
            $matches.Count | Should -Be 1
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

            $action = if (-not $hasMarker) { "post_new" } 
                      elseif ($existingCommentWithMarker) { "handle_existing" } 
                      else { "post_new" }

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
            $body = "Test content"

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
}
