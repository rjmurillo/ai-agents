#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Test-ClaudeAuthorization.ps1

.DESCRIPTION
    Comprehensive tests covering all authorization scenarios:
    - Valid authorization (MEMBER, OWNER, COLLABORATOR)
    - Bot allowlist authorization
    - Denied access (external contributors)
    - Missing @claude mention
    - Edge cases (null/empty values)
    - All event types
#>

BeforeAll {
    $script:ScriptPath = Join-Path $PSScriptRoot 'Test-ClaudeAuthorization.ps1'

    # Verify script exists
    if (-not (Test-Path $script:ScriptPath)) {
        throw "Script not found: $script:ScriptPath"
    }
}

Describe 'Test-ClaudeAuthorization' {
    Context 'Authorized Users - issue_comment event' {
        It 'Should authorize MEMBER with @claude mention' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'testuser' `
                -AuthorAssociation 'MEMBER' `
                -CommentBody 'Hey @claude, can you help with this?'

            $result | Should -Be 'true'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should authorize OWNER with @claude mention' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'repoowner' `
                -AuthorAssociation 'OWNER' `
                -CommentBody '@claude please review'

            $result | Should -Be 'true'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should authorize COLLABORATOR with @claude mention' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'collaborator' `
                -AuthorAssociation 'COLLABORATOR' `
                -CommentBody 'Can @claude help?'

            $result | Should -Be 'true'
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context 'Authorized Bots' {
        It 'Should authorize dependabot[bot] with @claude mention' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'dependabot[bot]' `
                -AuthorAssociation 'CONTRIBUTOR' `
                -CommentBody '@claude check this dependency update'

            $result | Should -Be 'true'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should authorize renovate[bot] with @claude mention' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'renovate[bot]' `
                -AuthorAssociation 'CONTRIBUTOR' `
                -CommentBody '@claude validate this'

            $result | Should -Be 'true'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should authorize github-actions[bot] with @claude mention' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'github-actions[bot]' `
                -AuthorAssociation 'NONE' `
                -CommentBody '@claude process this'

            $result | Should -Be 'true'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should prioritize bot allowlist over author association' {
            # Verify bot allowlist is checked before author association
            # github-actions[bot] with NONE association should be authorized via bot path
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'github-actions[bot]' `
                -AuthorAssociation 'NONE' `
                -CommentBody '@claude help'

            # Should authorize (bot allowlist takes precedence)
            $result | Should -Be 'true'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should authorize copilot[bot] with @claude mention' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'copilot[bot]' `
                -AuthorAssociation 'NONE' `
                -CommentBody '@claude can you review this?'

            $result | Should -Be 'true'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should authorize coderabbitai[bot] with @claude mention' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'coderabbitai[bot]' `
                -AuthorAssociation 'NONE' `
                -CommentBody '@claude please analyze'

            $result | Should -Be 'true'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should authorize cursor[bot] with @claude mention' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'cursor[bot]' `
                -AuthorAssociation 'NONE' `
                -CommentBody '@claude help with this code'

            $result | Should -Be 'true'
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context 'Denied Access' {
        It 'Should deny CONTRIBUTOR without @claude mention' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'external' `
                -AuthorAssociation 'CONTRIBUTOR' `
                -CommentBody 'This is a comment without mention'

            $result | Should -Be 'false'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should deny CONTRIBUTOR even with @claude mention' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'external' `
                -AuthorAssociation 'CONTRIBUTOR' `
                -CommentBody '@claude can you help?'

            $result | Should -Be 'false'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should deny MEMBER without @claude mention' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'member' `
                -AuthorAssociation 'MEMBER' `
                -CommentBody 'Just a regular comment'

            $result | Should -Be 'false'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should deny FIRST_TIME_CONTRIBUTOR with @claude mention' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'newuser' `
                -AuthorAssociation 'FIRST_TIME_CONTRIBUTOR' `
                -CommentBody '@claude please help'

            $result | Should -Be 'false'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should deny NONE author association with @claude mention' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'anonymous' `
                -AuthorAssociation 'NONE' `
                -CommentBody '@claude help please'

            $result | Should -Be 'false'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should deny bot not in allowlist even with @claude mention' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'some-other-bot[bot]' `
                -AuthorAssociation 'CONTRIBUTOR' `
                -CommentBody '@claude check this'

            $result | Should -Be 'false'
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context 'pull_request_review_comment event' {
        It 'Should authorize MEMBER with @claude mention in review comment' {
            $result = & $script:ScriptPath `
                -EventName 'pull_request_review_comment' `
                -Actor 'reviewer' `
                -AuthorAssociation 'MEMBER' `
                -CommentBody '@claude what do you think about this?'

            $result | Should -Be 'true'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should deny without @claude mention' {
            $result = & $script:ScriptPath `
                -EventName 'pull_request_review_comment' `
                -Actor 'reviewer' `
                -AuthorAssociation 'MEMBER' `
                -CommentBody 'Looks good to me'

            $result | Should -Be 'false'
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context 'pull_request_review event' {
        It 'Should authorize OWNER with @claude mention in review body' {
            $result = & $script:ScriptPath `
                -EventName 'pull_request_review' `
                -Actor 'owner' `
                -AuthorAssociation 'OWNER' `
                -ReviewBody '@claude please review the security implications'

            $result | Should -Be 'true'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should deny without @claude mention' {
            $result = & $script:ScriptPath `
                -EventName 'pull_request_review' `
                -Actor 'owner' `
                -AuthorAssociation 'OWNER' `
                -ReviewBody 'Approved'

            $result | Should -Be 'false'
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context 'issues event' {
        It 'Should authorize MEMBER with @claude mention in issue body' {
            $result = & $script:ScriptPath `
                -EventName 'issues' `
                -Actor 'member' `
                -AuthorAssociation 'MEMBER' `
                -IssueBody '@claude can you investigate this bug?'

            $result | Should -Be 'true'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should authorize MEMBER with @claude mention in issue title' {
            $result = & $script:ScriptPath `
                -EventName 'issues' `
                -Actor 'member' `
                -AuthorAssociation 'MEMBER' `
                -IssueTitle '@claude: Please help with feature request'

            $result | Should -Be 'true'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should authorize MEMBER with @claude in both title and body' {
            $result = & $script:ScriptPath `
                -EventName 'issues' `
                -Actor 'member' `
                -AuthorAssociation 'MEMBER' `
                -IssueBody 'Need help from @claude' `
                -IssueTitle '@claude Feature Request'

            $result | Should -Be 'true'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should deny without @claude mention in either title or body' {
            $result = & $script:ScriptPath `
                -EventName 'issues' `
                -Actor 'member' `
                -AuthorAssociation 'MEMBER' `
                -IssueTitle 'Bug Report' `
                -IssueBody 'There is a bug in the system'

            $result | Should -Be 'false'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should deny authorization when issues event has both empty body and empty title (no @claude mention)' {
            $result = & $script:ScriptPath `
                -EventName 'issues' `
                -Actor 'member' `
                -AuthorAssociation 'MEMBER' `
                -IssueBody '' `
                -IssueTitle ''

            $result | Should -Be 'false'
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context 'Edge Cases' {
        It 'Should deny authorization with empty comment body (no @claude mention)' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'member' `
                -AuthorAssociation 'MEMBER' `
                -CommentBody ''

            $result | Should -Be 'false'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should deny authorization with whitespace-only comment body (no @claude mention)' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'member' `
                -AuthorAssociation 'MEMBER' `
                -CommentBody '   '

            $result | Should -Be 'false'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should handle empty AuthorAssociation' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'unknown' `
                -AuthorAssociation '' `
                -CommentBody '@claude help'

            $result | Should -Be 'false'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should NOT match @CLAUDE in different test context (case-sensitive)' {
            # @claude matching is case-sensitive - @CLAUDE should not match
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'member' `
                -AuthorAssociation 'MEMBER' `
                -CommentBody '@CLAUDE help'

            $result | Should -Be 'false'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should detect @claude mention in middle of text' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'member' `
                -AuthorAssociation 'MEMBER' `
                -CommentBody 'This is a test. Can @claude help with this? Thanks!'

            $result | Should -Be 'true'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should not match partial @claude strings like @claudette' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'member' `
                -AuthorAssociation 'MEMBER' `
                -CommentBody 'Hey @claudette, can you help?'

            $result | Should -Be 'false'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should not match @claude followed by numbers like @claude123' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'member' `
                -AuthorAssociation 'MEMBER' `
                -CommentBody 'Hey @claude123, check this'

            $result | Should -Be 'false'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should not match @claude followed by underscore like @claude_bot' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'member' `
                -AuthorAssociation 'MEMBER' `
                -CommentBody 'Pinging @claude_bot for help'

            $result | Should -Be 'false'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should match @claude followed by punctuation like @claude!' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'member' `
                -AuthorAssociation 'MEMBER' `
                -CommentBody 'Hey @claude! Can you help?'

            $result | Should -Be 'true'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should match @claude at end of string' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'member' `
                -AuthorAssociation 'MEMBER' `
                -CommentBody 'Please help @claude'

            $result | Should -Be 'true'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should match @claude followed by comma' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'member' `
                -AuthorAssociation 'MEMBER' `
                -CommentBody '@claude, please review this'

            $result | Should -Be 'true'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should NOT match @Claude with capital C (case-sensitive)' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'member' `
                -AuthorAssociation 'MEMBER' `
                -CommentBody 'Hey @Claude, can you help?'

            $result | Should -Be 'false'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should NOT match @CLAUDE all uppercase (case-sensitive)' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'member' `
                -AuthorAssociation 'MEMBER' `
                -CommentBody '@CLAUDE please review'

            $result | Should -Be 'false'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should NOT match mixed case @ClAUDe (case-sensitive)' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'member' `
                -AuthorAssociation 'MEMBER' `
                -CommentBody 'Hey @ClAUDe, can you help?'

            $result | Should -Be 'false'
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context 'Input Size Validation' {
        It 'Should deny authorization for event body larger than 1MB with @claude before boundary' {
            # Create body with @claude before 1MB boundary but total size > 1MB
            $largeBody = '@claude help ' + ('x' * (1MB + 100))

            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'member' `
                -AuthorAssociation 'MEMBER' `
                -CommentBody $largeBody

            $result | Should -Be 'false'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should deny authorization for event body larger than 1MB with @claude after boundary' {
            # Create body with @claude after 1MB boundary
            $largeBody = ('x' * (1MB + 100)) + ' @claude help'

            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'member' `
                -AuthorAssociation 'MEMBER' `
                -CommentBody $largeBody

            $result | Should -Be 'false'
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context 'Script Error Handling' {
        It 'Should fail with invalid event type' {
            # ValidateSet throws a parameter binding exception before script execution
            { & $script:ScriptPath `
                -EventName 'invalid_event' `
                -Actor 'user' `
                -AuthorAssociation 'MEMBER' `
                -CommentBody '@claude help' `
                -ErrorAction Stop
            } | Should -Throw -ExceptionType ([System.Management.Automation.ParameterBindingException])
        }

        It 'Should handle runtime errors and log to summary' {
            # Arrange
            $env:GITHUB_STEP_SUMMARY = Join-Path $TestDrive 'summary.md'
            # Mock Get-Date in a way that error happens in try block
            # Since Get-Date is also used in catch block, this creates a double fault scenario
            Mock Get-Date { throw "Simulated runtime error" }

            # Act
            # Capture stderr to suppress error output, but preserve exit code
            $null = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'member' `
                -AuthorAssociation 'MEMBER' `
                -CommentBody '@claude help' `
                2>&1

            # Assert
            # Double fault: error in try block + error logging failure (exit code 2)
            $LASTEXITCODE | Should -Be 2

            # Cleanup
            if ($env:GITHUB_STEP_SUMMARY -and (Test-Path $env:GITHUB_STEP_SUMMARY)) {
                Remove-Item -Path $env:GITHUB_STEP_SUMMARY -ErrorAction SilentlyContinue
            }
            $env:GITHUB_STEP_SUMMARY = $null
        }
    }

    Context 'Audit Logging' {
        BeforeEach {
            # Create temporary summary file for testing
            $env:GITHUB_STEP_SUMMARY = Join-Path $TestDrive 'summary.md'
        }

        AfterEach {
            # Clean up
            if ($env:GITHUB_STEP_SUMMARY) {
                Remove-Item -Path $env:GITHUB_STEP_SUMMARY -ErrorAction SilentlyContinue
            }
            $env:GITHUB_STEP_SUMMARY = $null
        }

        It 'Should write audit log to GITHUB_STEP_SUMMARY when authorized' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'member' `
                -AuthorAssociation 'MEMBER' `
                -CommentBody '@claude help'

            $result | Should -Be 'true'
            $env:GITHUB_STEP_SUMMARY | Should -Exist

            $summary = Get-Content $env:GITHUB_STEP_SUMMARY -Raw
            $summary | Should -Match 'Claude Authorization Check'
            $summary | Should -Match 'issue_comment'
            $summary | Should -Match 'member'
            $summary | Should -Match 'MEMBER'
            $summary | Should -Match 'True'
        }

        It 'Should write audit log when denied' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'external' `
                -AuthorAssociation 'CONTRIBUTOR' `
                -CommentBody '@claude help'

            $result | Should -Be 'false'
            $env:GITHUB_STEP_SUMMARY | Should -Exist

            $summary = Get-Content $env:GITHUB_STEP_SUMMARY -Raw
            $summary | Should -Match 'False'
            $summary | Should -Match 'Access denied'
        }

        It 'Should handle null GITHUB_STEP_SUMMARY gracefully' {
            # Test without GITHUB_STEP_SUMMARY set
            # Script should succeed without trying to write audit log
            Remove-Item -Path $env:GITHUB_STEP_SUMMARY -ErrorAction SilentlyContinue
            $env:GITHUB_STEP_SUMMARY = $null

            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'member' `
                -AuthorAssociation 'MEMBER' `
                -CommentBody '@claude help'

            $result | Should -Be 'true'
            $LASTEXITCODE | Should -Be 0
            # Verify no summary file was created
            $env:GITHUB_STEP_SUMMARY | Should -BeNullOrEmpty
        }

        It 'Should write ISO 8601 timestamp format in audit log' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'member' `
                -AuthorAssociation 'MEMBER' `
                -CommentBody '@claude help'

            $result | Should -Be 'true'
            $env:GITHUB_STEP_SUMMARY | Should -Exist

            $summary = Get-Content $env:GITHUB_STEP_SUMMARY -Raw
            # ISO 8601 format: 2026-01-04T12:34:56.1234567-08:00
            $summary | Should -Match '\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'
        }

        It 'Should fail when GITHUB_STEP_SUMMARY write fails' {
            # Create a read-only summary file to force write failure
            $env:GITHUB_STEP_SUMMARY = Join-Path $TestDrive 'readonly_summary.md'
            New-Item -Path $env:GITHUB_STEP_SUMMARY -ItemType File -Force
            Set-ItemProperty -Path $env:GITHUB_STEP_SUMMARY -Name IsReadOnly -Value $true

            # Capture stderr to suppress error output, but preserve exit code
            $null = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'member' `
                -AuthorAssociation 'MEMBER' `
                -CommentBody '@claude help' `
                2>&1

            # Audit logging failure causes script error (exit code 1)
            # This is not a double fault - just audit log write failure
            $LASTEXITCODE | Should -Be 1

            # Cleanup
            Set-ItemProperty -Path $env:GITHUB_STEP_SUMMARY -Name IsReadOnly -Value $false
        }
    }
}
