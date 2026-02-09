#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Invoke-UserPromptMemoryCheck.ps1

.DESCRIPTION
    Tests the ADR-007 Memory-First Architecture user prompt hook.
    Validates keyword detection and context output for Claude.
#>

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot ".." ".claude" "hooks" "Invoke-UserPromptMemoryCheck.ps1"
}

Describe "Invoke-UserPromptMemoryCheck" {
    Context "Script execution" {
        It "Executes without error with empty input" {
            { '' | & $ScriptPath } | Should -Not -Throw
        }

        It "Returns exit code 0 with empty input" {
            '' | & $ScriptPath
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context "Keyword detection - planning keywords" {
        It "Detects 'plan' keyword" {
            $TestInput = '{"prompt": "help me plan this feature"}'
            $Output = $TestInput | & $ScriptPath
            $Output | Should -Match "ADR-007"
        }

        It "Detects 'implement' keyword" {
            $TestInput = '{"prompt": "implement the login feature"}'
            $Output = $TestInput | & $ScriptPath
            $Output | Should -Match "ADR-007"
        }

        It "Detects 'design' keyword" {
            $TestInput = '{"prompt": "design the database schema"}'
            $Output = $TestInput | & $ScriptPath
            $Output | Should -Match "ADR-007"
        }

        It "Detects 'architect' keyword" {
            $TestInput = '{"prompt": "architect the solution"}'
            $Output = $TestInput | & $ScriptPath
            $Output | Should -Match "ADR-007"
        }

        It "Detects 'refactor' keyword" {
            $TestInput = '{"prompt": "refactor the code"}'
            $Output = $TestInput | & $ScriptPath
            $Output | Should -Match "ADR-007"
        }
    }

    Context "Keyword detection - action keywords" {
        It "Detects 'fix' keyword" {
            $TestInput = '{"prompt": "fix the bug in authentication"}'
            $Output = $TestInput | & $ScriptPath
            $Output | Should -Match "ADR-007"
        }

        It "Detects 'add' keyword" {
            $TestInput = '{"prompt": "add a new endpoint"}'
            $Output = $TestInput | & $ScriptPath
            $Output | Should -Match "ADR-007"
        }

        It "Detects 'update' keyword" {
            $TestInput = '{"prompt": "update the configuration"}'
            $Output = $TestInput | & $ScriptPath
            $Output | Should -Match "ADR-007"
        }

        It "Detects 'create' keyword" {
            $TestInput = '{"prompt": "create a new service"}'
            $Output = $TestInput | & $ScriptPath
            $Output | Should -Match "ADR-007"
        }

        It "Detects 'build' keyword" {
            $TestInput = '{"prompt": "build the module"}'
            $Output = $TestInput | & $ScriptPath
            $Output | Should -Match "ADR-007"
        }
    }

    Context "Keyword detection - GitHub keywords" {
        It "Detects 'feature' keyword" {
            $TestInput = '{"prompt": "work on the feature"}'
            $Output = $TestInput | & $ScriptPath
            $Output | Should -Match "ADR-007"
        }

        It "Detects 'issue' keyword" {
            $TestInput = '{"prompt": "resolve this issue"}'
            $Output = $TestInput | & $ScriptPath
            $Output | Should -Match "ADR-007"
        }

        It "Detects 'pr' keyword" {
            $TestInput = '{"prompt": "review the pr"}'
            $Output = $TestInput | & $ScriptPath
            $Output | Should -Match "ADR-007"
        }
    }

    Context "No output for non-matching prompts" {
        It "Outputs nothing for simple greeting" {
            $TestInput = '{"prompt": "hello"}'
            $Output = $TestInput | & $ScriptPath
            $Output | Should -BeNullOrEmpty
        }

        It "Outputs nothing for question about status" {
            $TestInput = '{"prompt": "what is the status of the project?"}'
            $Output = $TestInput | & $ScriptPath
            $Output | Should -BeNullOrEmpty
        }

        It "Outputs nothing for documentation request" {
            $TestInput = '{"prompt": "show me the readme"}'
            $Output = $TestInput | & $ScriptPath
            $Output | Should -BeNullOrEmpty
        }
    }

    Context "Case insensitivity" {
        It "Detects uppercase keywords" {
            $TestInput = '{"prompt": "IMPLEMENT the feature"}'
            $Output = $TestInput | & $ScriptPath
            $Output | Should -Match "ADR-007"
        }

        It "Detects mixed case keywords" {
            $TestInput = '{"prompt": "ImPlEmEnT the feature"}'
            $Output = $TestInput | & $ScriptPath
            $Output | Should -Match "ADR-007"
        }
    }

    Context "Output content verification" {
        BeforeAll {
            $TestInput = '{"prompt": "implement the feature"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
        }

        It "Includes memory-index reference" {
            $Output | Should -Match "memory-index"
        }

        It "Includes session log reference" {
            $Output | Should -Match "session log"
        }

        It "Includes ADR-007 label" {
            $Output | Should -Match "ADR-007"
        }
    }

    Context "JSON parsing" {
        It "Handles malformed JSON gracefully" {
            $TestInput = 'not valid json'
            { $TestInput | & $ScriptPath } | Should -Not -Throw
        }

        It "Handles missing prompt field" {
            $TestInput = '{"other": "field"}'
            { $TestInput | & $ScriptPath } | Should -Not -Throw
        }
    }

    Context "PR creation detection" {
        It "Detects 'create pr' keyword" {
            $TestInput = '{"prompt": "create pr for this feature"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Pre-PR gate"
        }

        It "Detects 'open pull request' keyword" {
            $TestInput = '{"prompt": "open pull request"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Pre-PR gate"
        }

        It "Detects 'gh pr create' command" {
            $TestInput = '{"prompt": "run gh pr create"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Pre-PR gate"
        }

        It "Includes test validation directive" {
            $TestInput = '{"prompt": "create pr"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Run tests"
        }

        It "Includes memory naming check" {
            $TestInput = '{"prompt": "create pr"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "skill-.*prefix"
        }

        It "Includes validation memory reference" {
            $TestInput = '{"prompt": "create pr"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "validation-pre-pr-checklist"
        }

        It "Includes syntax validation directive" {
            $TestInput = '{"prompt": "create pr"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "validate syntax"
        }

        It "Does not trigger on simple 'pr' mention" {
            $TestInput = '{"prompt": "review the pr"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Not -Match "Pre-PR gate"
        }
    }

    Context "GitHub CLI detection - gh pr commands" {
        It "Detects 'gh pr create' command" {
            $TestInput = '{"prompt": "use gh pr create to open the PR"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
            $Output | Should -Match "gh pr create"
        }

        It "Detects 'gh pr list' command" {
            $TestInput = '{"prompt": "run gh pr list to see PRs"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
        }

        It "Detects 'gh pr view' command" {
            $TestInput = '{"prompt": "execute gh pr view 123"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
        }

        It "Detects 'gh pr merge' command" {
            $TestInput = '{"prompt": "run gh pr merge 456"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
        }

        It "Detects 'gh pr close' command" {
            $TestInput = '{"prompt": "use gh pr close 789"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
        }

        It "Detects 'gh pr checks' command" {
            $TestInput = '{"prompt": "run gh pr checks 123"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
        }

        It "Detects 'gh pr review' command" {
            $TestInput = '{"prompt": "execute gh pr review 456 --approve"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
        }

        It "Detects 'gh pr comment' command" {
            $TestInput = '{"prompt": "use gh pr comment 789 --body text"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
        }

        It "Detects 'gh pr diff' command" {
            $TestInput = '{"prompt": "run gh pr diff 123"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
        }

        It "Detects 'gh pr ready' command" {
            $TestInput = '{"prompt": "execute gh pr ready 456"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
        }

        It "Detects 'gh pr status' command" {
            $TestInput = '{"prompt": "run gh pr status"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
        }
    }

    Context "GitHub CLI detection - gh issue commands" {
        It "Detects 'gh issue create' command" {
            $TestInput = '{"prompt": "use gh issue create --title Bug"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
            $Output | Should -Match "gh issue create"
        }

        It "Detects 'gh issue list' command" {
            $TestInput = '{"prompt": "run gh issue list --state open"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
        }

        It "Detects 'gh issue view' command" {
            $TestInput = '{"prompt": "execute gh issue view 123"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
        }

        It "Detects 'gh issue close' command" {
            $TestInput = '{"prompt": "use gh issue close 456"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
        }

        It "Detects 'gh issue comment' command" {
            $TestInput = '{"prompt": "run gh issue comment 789 --body response"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
        }

        It "Detects 'gh issue edit' command" {
            $TestInput = '{"prompt": "execute gh issue edit 123 --add-label bug"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
        }
    }

    Context "GitHub CLI detection - gh api commands" {
        It "Detects 'gh api' command" {
            $TestInput = '{"prompt": "use gh api repos/owner/repo/pulls"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
            $Output | Should -Match "gh api"
        }

        It "Detects 'gh api' with GraphQL" {
            $TestInput = '{"prompt": "run gh api graphql -f query=..."}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
        }

        It "Detects 'gh api' POST request" {
            $TestInput = '{"prompt": "execute gh api -X POST repos/owner/repo/issues"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
        }
    }

    Context "GitHub CLI detection - gh run/workflow commands" {
        It "Detects 'gh run' command" {
            $TestInput = '{"prompt": "use gh run list"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
            $Output | Should -Match "gh run"
        }

        It "Detects 'gh run view' command" {
            $TestInput = '{"prompt": "run gh run view 12345"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
        }

        It "Detects 'gh run watch' command" {
            $TestInput = '{"prompt": "execute gh run watch 12345"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
        }

        It "Detects 'gh workflow' command" {
            $TestInput = '{"prompt": "use gh workflow list"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
            $Output | Should -Match "gh workflow"
        }

        It "Detects 'gh workflow run' command" {
            $TestInput = '{"prompt": "execute gh workflow run ci.yml"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
        }
    }

    Context "GitHub CLI detection - case insensitivity" {
        It "Detects uppercase 'GH PR CREATE'" {
            $TestInput = '{"prompt": "run GH PR CREATE"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
        }

        It "Detects mixed case 'Gh Issue List'" {
            $TestInput = '{"prompt": "use Gh Issue List"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
        }

        It "Detects uppercase 'GH API'" {
            $TestInput = '{"prompt": "execute GH API repos/owner/repo"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Skill-first"
        }
    }

    Context "GitHub CLI detection - output content verification" {
        BeforeAll {
            $TestInput = '{"prompt": "run gh pr merge 123"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
        }

        It "References SKILL.md documentation" {
            $Output | Should -Match "\.claude/skills/github/SKILL\.md"
        }

        It "Includes detected command name" {
            $Output | Should -Match "gh pr merge"
        }

        It "Includes skill alternative directive" {
            $Output | Should -Match "skill alternative"
        }

        It "Uses Skill-first label" {
            $Output | Should -Match "Skill-first"
        }
    }

    Context "GitHub CLI detection - non-triggering patterns" {
        It "Does not trigger on 'github' word alone" {
            $TestInput = '{"prompt": "check the github repository"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Not -Match "Skill-first"
        }

        It "Does not trigger on 'gh' word alone" {
            $TestInput = '{"prompt": "the gh tool is useful"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            # Note: 'gh' alone does not match - we need 'gh pr', 'gh issue', etc.
            $Output | Should -Not -Match "Skill-first"
        }

        It "Does not trigger on partial command 'pr'" {
            $TestInput = '{"prompt": "check the pr status manually"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            # 'pr' alone triggers ADR-007 but not Skill Usage Check
            $Output | Should -Not -Match "Skill-first"
        }
    }

    Context "Multiple triggers in single prompt" {
        It "Shows both ADR-007 and Skill Usage Check for implementation with gh command" {
            $TestInput = '{"prompt": "implement feature using gh pr create"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "ADR-007"
            $Output | Should -Match "Skill-first"
        }

        It "Shows both Pre-PR and Skill Usage Check for PR creation with gh command" {
            $TestInput = '{"prompt": "create pr using gh pr create"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "Pre-PR gate"
            $Output | Should -Match "Skill-first"
        }

        It "Shows all three checks when applicable" {
            $TestInput = '{"prompt": "implement the feature then create pr with gh pr create"}'
            $Output = ($TestInput | & $ScriptPath) -join "`n"
            $Output | Should -Match "ADR-007"
            $Output | Should -Match "Pre-PR gate"
            $Output | Should -Match "Skill-first"
        }
    }
}
