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
    }

    Context 'Edge Cases' {
        It 'Should handle empty comment body gracefully' {
            $result = & $script:ScriptPath `
                -EventName 'issue_comment' `
                -Actor 'member' `
                -AuthorAssociation 'MEMBER' `
                -CommentBody ''

            $result | Should -Be 'false'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Should handle whitespace-only comment body' {
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

        It 'Should handle @claude mention case-sensitively' {
            # @claude is case-sensitive in GitHub mentions
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
    }

    Context 'Audit Logging' {
        BeforeEach {
            # Create temporary summary file for testing
            $env:GITHUB_STEP_SUMMARY = Join-Path $TestDrive 'summary.md'
        }

        AfterEach {
            # Clean up
            Remove-Item -Path $env:GITHUB_STEP_SUMMARY -ErrorAction SilentlyContinue
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
    }
}
