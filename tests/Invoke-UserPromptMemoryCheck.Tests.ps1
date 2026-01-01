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
            $Input = '{"prompt": "help me plan this feature"}'
            $Output = $Input | & $ScriptPath
            $Output | Should -Match "ADR-007 Memory Check"
        }

        It "Detects 'implement' keyword" {
            $Input = '{"prompt": "implement the login feature"}'
            $Output = $Input | & $ScriptPath
            $Output | Should -Match "ADR-007 Memory Check"
        }

        It "Detects 'design' keyword" {
            $Input = '{"prompt": "design the database schema"}'
            $Output = $Input | & $ScriptPath
            $Output | Should -Match "ADR-007 Memory Check"
        }

        It "Detects 'architect' keyword" {
            $Input = '{"prompt": "architect the solution"}'
            $Output = $Input | & $ScriptPath
            $Output | Should -Match "ADR-007 Memory Check"
        }

        It "Detects 'refactor' keyword" {
            $Input = '{"prompt": "refactor the code"}'
            $Output = $Input | & $ScriptPath
            $Output | Should -Match "ADR-007 Memory Check"
        }
    }

    Context "Keyword detection - action keywords" {
        It "Detects 'fix' keyword" {
            $Input = '{"prompt": "fix the bug in authentication"}'
            $Output = $Input | & $ScriptPath
            $Output | Should -Match "ADR-007 Memory Check"
        }

        It "Detects 'add' keyword" {
            $Input = '{"prompt": "add a new endpoint"}'
            $Output = $Input | & $ScriptPath
            $Output | Should -Match "ADR-007 Memory Check"
        }

        It "Detects 'update' keyword" {
            $Input = '{"prompt": "update the configuration"}'
            $Output = $Input | & $ScriptPath
            $Output | Should -Match "ADR-007 Memory Check"
        }

        It "Detects 'create' keyword" {
            $Input = '{"prompt": "create a new service"}'
            $Output = $Input | & $ScriptPath
            $Output | Should -Match "ADR-007 Memory Check"
        }

        It "Detects 'build' keyword" {
            $Input = '{"prompt": "build the module"}'
            $Output = $Input | & $ScriptPath
            $Output | Should -Match "ADR-007 Memory Check"
        }
    }

    Context "Keyword detection - GitHub keywords" {
        It "Detects 'feature' keyword" {
            $Input = '{"prompt": "work on the feature"}'
            $Output = $Input | & $ScriptPath
            $Output | Should -Match "ADR-007 Memory Check"
        }

        It "Detects 'issue' keyword" {
            $Input = '{"prompt": "resolve this issue"}'
            $Output = $Input | & $ScriptPath
            $Output | Should -Match "ADR-007 Memory Check"
        }

        It "Detects 'pr' keyword" {
            $Input = '{"prompt": "review the pr"}'
            $Output = $Input | & $ScriptPath
            $Output | Should -Match "ADR-007 Memory Check"
        }
    }

    Context "No output for non-matching prompts" {
        It "Outputs nothing for simple greeting" {
            $Input = '{"prompt": "hello"}'
            $Output = $Input | & $ScriptPath
            $Output | Should -BeNullOrEmpty
        }

        It "Outputs nothing for question about status" {
            $Input = '{"prompt": "what is the status of the project?"}'
            $Output = $Input | & $ScriptPath
            $Output | Should -BeNullOrEmpty
        }

        It "Outputs nothing for documentation request" {
            $Input = '{"prompt": "show me the readme"}'
            $Output = $Input | & $ScriptPath
            $Output | Should -BeNullOrEmpty
        }
    }

    Context "Case insensitivity" {
        It "Detects uppercase keywords" {
            $Input = '{"prompt": "IMPLEMENT the feature"}'
            $Output = $Input | & $ScriptPath
            $Output | Should -Match "ADR-007 Memory Check"
        }

        It "Detects mixed case keywords" {
            $Input = '{"prompt": "ImPlEmEnT the feature"}'
            $Output = $Input | & $ScriptPath
            $Output | Should -Match "ADR-007 Memory Check"
        }
    }

    Context "Output content verification" {
        BeforeAll {
            $Input = '{"prompt": "implement the feature"}'
            $Output = ($Input | & $ScriptPath) -join "`n"
        }

        It "Includes memory-index reference" {
            $Output | Should -Match "memory-index"
        }

        It "Includes Forgetful reference" {
            $Output | Should -Match "Forgetful"
        }

        It "Includes session log reference" {
            $Output | Should -Match "session log"
        }
    }

    Context "JSON parsing" {
        It "Handles malformed JSON gracefully" {
            $Input = 'not valid json'
            { $Input | & $ScriptPath } | Should -Not -Throw
        }

        It "Handles missing prompt field" {
            $Input = '{"other": "field"}'
            { $Input | & $ScriptPath } | Should -Not -Throw
        }
    }
}
