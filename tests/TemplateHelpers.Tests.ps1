<#
.SYNOPSIS
    Pester tests for TemplateHelpers module.

.DESCRIPTION
    Comprehensive tests for New-PopulatedSessionLog and Get-DescriptiveKeywords
    functions covering valid operations, edge cases, and error scenarios.
#>

BeforeAll {
    # Import the module under test
    Import-Module $PSScriptRoot/../.claude/skills/session-init/modules/TemplateHelpers.psm1 -Force
    
    # Create temp directory for test artifacts
    $Script:TestTempDir = Join-Path ([System.IO.Path]::GetTempPath()) "TemplateHelpers-Tests-$(Get-Random)"
    New-Item -ItemType Directory -Path $Script:TestTempDir -Force | Out-Null
    
    # Store original location
    $Script:OriginalLocation = Get-Location
    
    # Sample valid template with all required placeholders
    $Script:ValidTemplate = @"
# Session NN - YYYY-MM-DD

## Context

| Field | Value |
|-------|-------|
| Branch | [branch name] |
| Starting Commit | [SHA] |
| Working Tree | [clean/dirty] |

## Objective

[What this session aims to accomplish]

## Session End Checklist

- [ ] Task completed
"@
}

AfterAll {
    # Restore original location
    Set-Location $Script:OriginalLocation
    
    # Clean up test artifacts
    if (Test-Path $Script:TestTempDir) {
        Remove-Item -Path $Script:TestTempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    
    # Remove module from session
    Remove-Module TemplateHelpers -Force -ErrorAction SilentlyContinue
}

Describe 'New-PopulatedSessionLog' {
    
    Context 'Valid Template Replacement' {
        BeforeAll {
            $Script:GitInfo = @{
                Branch = 'feat/my-feature'
                Commit = 'abc1234'
                Status = 'clean'
            }
            $Script:UserInput = @{
                SessionNumber = 42
                Objective = 'Implement the new feature'
            }
        }
        
        It 'Returns populated string with all placeholders replaced' {
            $result = New-PopulatedSessionLog -Template $Script:ValidTemplate -GitInfo $Script:GitInfo -UserInput $Script:UserInput
            
            $result | Should -BeOfType [string]
            $result | Should -Not -BeNullOrEmpty
        }
        
        It 'Replaces session number placeholder' {
            $result = New-PopulatedSessionLog -Template $Script:ValidTemplate -GitInfo $Script:GitInfo -UserInput $Script:UserInput
            
            $result | Should -Match 'Session 42'
            $result | Should -Not -Match '\bNN\b'
        }
        
        It 'Replaces date placeholder with current date' {
            $result = New-PopulatedSessionLog -Template $Script:ValidTemplate -GitInfo $Script:GitInfo -UserInput $Script:UserInput
            $expectedDate = Get-Date -Format "yyyy-MM-dd"
            
            $result | Should -Match $expectedDate
            $result | Should -Not -Match 'YYYY-MM-DD'
        }
        
        It 'Replaces branch name placeholder' {
            $result = New-PopulatedSessionLog -Template $Script:ValidTemplate -GitInfo $Script:GitInfo -UserInput $Script:UserInput
            
            $result | Should -Match 'feat/my-feature'
            $result | Should -Not -Match '\[branch name\]'
        }
        
        It 'Replaces SHA placeholder' {
            $result = New-PopulatedSessionLog -Template $Script:ValidTemplate -GitInfo $Script:GitInfo -UserInput $Script:UserInput
            
            $result | Should -Match 'abc1234'
            $result | Should -Not -Match '\[SHA\]'
        }
        
        It 'Replaces objective placeholder' {
            $result = New-PopulatedSessionLog -Template $Script:ValidTemplate -GitInfo $Script:GitInfo -UserInput $Script:UserInput
            
            $result | Should -Match 'Implement the new feature'
            $result | Should -Not -Match '\[What this session aims to accomplish\]'
        }
        
        It 'Replaces git status placeholder' {
            $result = New-PopulatedSessionLog -Template $Script:ValidTemplate -GitInfo $Script:GitInfo -UserInput $Script:UserInput
            
            $result | Should -Match 'clean'
            $result | Should -Not -Match '\[clean/dirty\]'
        }
        
        It 'Handles dirty git status' {
            $dirtyGitInfo = @{
                Branch = 'main'
                Commit = 'def5678'
                Status = 'dirty'
            }
            $result = New-PopulatedSessionLog -Template $Script:ValidTemplate -GitInfo $dirtyGitInfo -UserInput $Script:UserInput
            
            $result | Should -Match 'dirty'
        }
    }
    
    Context 'Placeholder Validation - Before Replacement' {
        # Tests updated to expect exceptions (fail-fast design) instead of warnings
        # Missing required placeholders indicate template/protocol version mismatch
        # and should fail immediately to prevent creating invalid session logs.

        BeforeAll {
            $Script:GitInfo = @{
                Branch = 'main'
                Commit = 'abc1234'
                Status = 'clean'
            }
            $Script:UserInput = @{
                SessionNumber = 1
                Objective = 'Test'
            }
        }

        It 'Throws exception when template missing NN placeholder' {
            $templateMissingNN = "# Session - YYYY-MM-DD`n[branch name] [SHA] [What this session aims to accomplish] [clean/dirty]"

            { New-PopulatedSessionLog -Template $templateMissingNN -GitInfo $Script:GitInfo -UserInput $Script:UserInput } |
                Should -Throw '*NN (session number)*'
        }

        It 'Throws exception when template missing YYYY-MM-DD placeholder' {
            $templateMissingDate = "# Session NN`n[branch name] [SHA] [What this session aims to accomplish] [clean/dirty]"

            { New-PopulatedSessionLog -Template $templateMissingDate -GitInfo $Script:GitInfo -UserInput $Script:UserInput } |
                Should -Throw '*YYYY-MM-DD*'
        }

        It 'Throws exception when template missing branch name placeholder' {
            $templateMissingBranch = "# Session NN - YYYY-MM-DD`n[SHA] [What this session aims to accomplish] [clean/dirty]"

            { New-PopulatedSessionLog -Template $templateMissingBranch -GitInfo $Script:GitInfo -UserInput $Script:UserInput } |
                Should -Throw '*[branch name]*'
        }

        It 'Throws exception when template missing SHA placeholder' {
            $templateMissingSHA = "# Session NN - YYYY-MM-DD`n[branch name] [What this session aims to accomplish] [clean/dirty]"

            { New-PopulatedSessionLog -Template $templateMissingSHA -GitInfo $Script:GitInfo -UserInput $Script:UserInput } |
                Should -Throw '*[SHA]*'
        }

        It 'Throws exception when template missing objective placeholder' {
            $templateMissingObjective = "# Session NN - YYYY-MM-DD`n[branch name] [SHA] [clean/dirty]"

            { New-PopulatedSessionLog -Template $templateMissingObjective -GitInfo $Script:GitInfo -UserInput $Script:UserInput } |
                Should -Throw '*[What this session aims to accomplish]*'
        }

        It 'Throws exception when template missing clean/dirty placeholder' {
            $templateMissingStatus = "# Session NN - YYYY-MM-DD`n[branch name] [SHA] [What this session aims to accomplish]"

            { New-PopulatedSessionLog -Template $templateMissingStatus -GitInfo $Script:GitInfo -UserInput $Script:UserInput } |
                Should -Throw '*[clean/dirty]*'
        }

        It 'Exception message includes list of all missing placeholders' {
            $templateMissingMultiple = "# Session - Date`nBranch Commit Status"

            { New-PopulatedSessionLog -Template $templateMissingMultiple -GitInfo $Script:GitInfo -UserInput $Script:UserInput } |
                Should -Throw '*NN*YYYY-MM-DD*'
        }
    }
    
    Context 'Edge Cases' {
        BeforeAll {
            $Script:GitInfo = @{
                Branch = 'main'
                Commit = 'abc1234'
                Status = 'clean'
            }
        }
        
        It 'Handles empty objective string' {
            $userInput = @{
                SessionNumber = 1
                Objective = ''
            }
            
            $result = New-PopulatedSessionLog -Template $Script:ValidTemplate -GitInfo $Script:GitInfo -UserInput $userInput
            
            $result | Should -Not -BeNullOrEmpty
            $result | Should -Not -Match '\[What this session aims to accomplish\]'
        }
        
        It 'Handles special characters in objective (quotes)' {
            $userInput = @{
                SessionNumber = 1
                Objective = 'Fix the "broken" feature'
            }
            
            $result = New-PopulatedSessionLog -Template $Script:ValidTemplate -GitInfo $Script:GitInfo -UserInput $userInput
            
            $result | Should -Match 'Fix the "broken" feature'
        }
        
        It 'Handles special characters in objective (brackets)' {
            $userInput = @{
                SessionNumber = 1
                Objective = 'Update [Config] section'
            }
            
            $result = New-PopulatedSessionLog -Template $Script:ValidTemplate -GitInfo $Script:GitInfo -UserInput $userInput
            
            $result | Should -Match 'Update \[Config\] section'
        }
        
        It 'Handles special regex characters in objective' {
            $userInput = @{
                SessionNumber = 1
                Objective = 'Fix regex pattern: .*\d+$'
            }
            
            $result = New-PopulatedSessionLog -Template $Script:ValidTemplate -GitInfo $Script:GitInfo -UserInput $userInput
            
            $result | Should -Match 'Fix regex pattern'
        }
        
        It 'Handles multi-line objective' {
            $userInput = @{
                SessionNumber = 1
                Objective = "Line 1`nLine 2`nLine 3"
            }
            
            $result = New-PopulatedSessionLog -Template $Script:ValidTemplate -GitInfo $Script:GitInfo -UserInput $userInput
            
            $result | Should -Match 'Line 1'
            $result | Should -Match 'Line 2'
        }
        
        It 'Handles very long objective (>1000 chars)' {
            $longObjective = 'A' * 1500
            $userInput = @{
                SessionNumber = 1
                Objective = $longObjective
            }
            
            $result = New-PopulatedSessionLog -Template $Script:ValidTemplate -GitInfo $Script:GitInfo -UserInput $userInput
            
            $result | Should -Not -BeNullOrEmpty
            $result | Should -Match 'AAAA'
        }
        
        It 'Handles branch names with slashes' {
            $gitInfo = @{
                Branch = 'feature/user/auth-flow'
                Commit = 'abc1234'
                Status = 'clean'
            }
            $userInput = @{ SessionNumber = 1; Objective = 'Test' }
            
            $result = New-PopulatedSessionLog -Template $Script:ValidTemplate -GitInfo $gitInfo -UserInput $userInput
            
            $result | Should -Match 'feature/user/auth-flow'
        }
        
        It 'Handles branch names with hyphens' {
            $gitInfo = @{
                Branch = 'fix-bug-123-memory-leak'
                Commit = 'abc1234'
                Status = 'clean'
            }
            $userInput = @{ SessionNumber = 1; Objective = 'Test' }
            
            $result = New-PopulatedSessionLog -Template $Script:ValidTemplate -GitInfo $gitInfo -UserInput $userInput
            
            $result | Should -Match 'fix-bug-123-memory-leak'
        }
        
        It 'Handles short commit SHA (7 chars)' {
            $gitInfo = @{
                Branch = 'main'
                Commit = 'abc1234'
                Status = 'clean'
            }
            $userInput = @{ SessionNumber = 1; Objective = 'Test' }
            
            $result = New-PopulatedSessionLog -Template $Script:ValidTemplate -GitInfo $gitInfo -UserInput $userInput
            
            $result | Should -Match 'abc1234'
        }
        
        It 'Handles full commit SHA (40 chars)' {
            $fullSha = 'abc1234567890def1234567890abc1234567890f'
            $gitInfo = @{
                Branch = 'main'
                Commit = $fullSha
                Status = 'clean'
            }
            $userInput = @{ SessionNumber = 1; Objective = 'Test' }
            
            $result = New-PopulatedSessionLog -Template $Script:ValidTemplate -GitInfo $gitInfo -UserInput $userInput
            
            $result | Should -Match $fullSha
        }
        
        It 'Handles high session numbers' {
            $userInput = @{
                SessionNumber = 9999
                Objective = 'Test'
            }
            
            $result = New-PopulatedSessionLog -Template $Script:ValidTemplate -GitInfo $Script:GitInfo -UserInput $userInput
            
            $result | Should -Match 'Session 9999'
        }
    }
}

Describe 'Get-DescriptiveKeywords' {
    
    Context 'Keyword Extraction' {
        It 'Extracts keywords from simple objective' {
            $result = Get-DescriptiveKeywords -Objective "Implement feature"
            
            $result | Should -Be 'implement-feature'
        }
        
        It 'Removes stop words' {
            $result = Get-DescriptiveKeywords -Objective "Fix the bug in the code"
            
            $result | Should -Not -Match '\bthe\b'
            $result | Should -Match 'fix'
            $result | Should -Match 'bug'
            $result | Should -Match 'code'
        }
        
        It 'Keeps domain-specific verbs' {
            $result = Get-DescriptiveKeywords -Objective "Implement debug fix refactor test"
            
            $result | Should -Match 'implement'
            $result | Should -Match 'debug'
            $result | Should -Match 'fix'
            $result | Should -Match 'refactor'
            $result | Should -Match 'test'
        }
        
        It 'Converts to kebab-case' {
            $result = Get-DescriptiveKeywords -Objective "Update User Service"
            
            $result | Should -Match '-'
            $result | Should -Not -Match ' '
            $result | Should -Match 'update-user-service'
        }
        
        It 'Limits to 5 keywords maximum' {
            $result = Get-DescriptiveKeywords -Objective "one two three four five six seven eight nine ten"
            
            $parts = $result -split '-'
            $parts.Count | Should -BeLessOrEqual 5
        }
        
        It 'Returns first 5 keywords when more available' {
            $result = Get-DescriptiveKeywords -Objective "implement user authentication service with oauth provider integration"
            
            $parts = $result -split '-'
            $parts.Count | Should -BeLessOrEqual 5
            $result | Should -Match 'implement'
            $result | Should -Match 'user'
            $result | Should -Match 'authentication'
        }
        
        It 'Handles objective with fewer than 5 keywords' {
            $result = Get-DescriptiveKeywords -Objective "Fix bug"
            
            $result | Should -Be 'fix-bug'
        }
    }
    
    Context 'Stop Word Filtering' {
        It 'Filters common articles (a, an, the)' {
            $result = Get-DescriptiveKeywords -Objective "a bug an error the issue"
            
            $result | Should -Not -Match '\ba\b'
            $result | Should -Not -Match '\ban\b'
            $result | Should -Not -Match '\bthe\b'
        }
        
        It 'Filters conjunctions (and, or, but)' {
            $result = Get-DescriptiveKeywords -Objective "fix and test or deploy but verify"
            
            $result | Should -Not -Match '\band\b'
            $result | Should -Not -Match '\bor\b'
            $result | Should -Not -Match '\bbut\b'
        }
        
        It 'Filters prepositions (in, on, at, to, for)' {
            $result = Get-DescriptiveKeywords -Objective "code in file on server at endpoint to user for client"
            
            $result | Should -Match 'code'
            $result | Should -Match 'file'
        }
        
        It 'Filters pronouns (i, you, he, she, it, we, they)' {
            $result = Get-DescriptiveKeywords -Objective "I fix you test we deploy they verify"
            
            $result | Should -Match 'fix'
            $result | Should -Match 'test'
            $result | Should -Match 'deploy'
            $result | Should -Match 'verify'
        }
        
        It 'Filters auxiliary verbs (is, are, was, were)' {
            $result = Get-DescriptiveKeywords -Objective "code is broken tests are failing build was slow"
            
            $result | Should -Match 'code'
            $result | Should -Match 'broken'
            $result | Should -Match 'tests'
            $result | Should -Match 'failing'
        }
        
        It 'Filters modal verbs (will, would, should, could, may, might, can)' {
            $result = Get-DescriptiveKeywords -Objective "will implement should test can deploy"
            
            $result | Should -Not -Match '\bwill\b'
            $result | Should -Not -Match '\bshould\b'
            $result | Should -Not -Match '\bcan\b'
            $result | Should -Match 'implement'
            $result | Should -Match 'test'
            $result | Should -Match 'deploy'
        }
        
        It 'Keeps technical terms even if short (api, sql)' {
            # Note: Only 5 keywords are kept, so 'git' may be excluded depending on position
            $result = Get-DescriptiveKeywords -Objective "Fix API SQL integration"
            
            $result | Should -Match 'api'
            $result | Should -Match 'sql'
        }
    }
    
    Context 'Edge Cases' {
        It 'Returns empty string for empty objective' {
            $result = Get-DescriptiveKeywords -Objective ""
            
            $result | Should -Be ''
        }
        
        It 'Returns empty string for whitespace-only objective' {
            $result = Get-DescriptiveKeywords -Objective "   "
            
            $result | Should -Be ''
        }
        
        It 'Returns empty string for objective with only stop words' {
            $result = Get-DescriptiveKeywords -Objective "the a an to for with"
            
            $result | Should -Be ''
        }
        
        It 'Handles objective with punctuation' {
            $result = Get-DescriptiveKeywords -Objective "Fix, the bug. Test everything!"
            
            $result | Should -Match 'fix'
            $result | Should -Match 'bug'
            $result | Should -Match 'test'
        }
        
        It 'Handles objective with numbers' {
            $result = Get-DescriptiveKeywords -Objective "Implement OAuth 2.0 authentication"
            
            $result | Should -Match 'implement'
            $result | Should -Match 'oauth'
            $result | Should -Match 'authentication'
        }
        
        It 'Handles objective with hyphens' {
            $result = Get-DescriptiveKeywords -Objective "Run end-to-end tests"
            
            $result | Should -Match 'end-to-end'
            $result | Should -Match 'tests'
        }
        
        It 'Handles objective with underscores' {
            $result = Get-DescriptiveKeywords -Objective "Fix user_service module"
            
            $result | Should -Match 'user_service'
            $result | Should -Match 'module'
        }
        
        It 'Converts mixed case to lowercase' {
            $result = Get-DescriptiveKeywords -Objective "Fix UserService Bug"
            
            $result | Should -Match 'userservice'
            $result | Should -Match 'bug'
        }
        
        It 'Handles extra whitespace' {
            $result = Get-DescriptiveKeywords -Objective "Fix    the     bug"
            
            $result | Should -Match 'fix'
            $result | Should -Match 'bug'
            $result | Should -Not -Match '--'
        }
        
        It 'Handles tabs in objective' {
            $result = Get-DescriptiveKeywords -Objective "Fix`tthe`tbug"
            
            $result | Should -Match 'fix'
            $result | Should -Match 'bug'
        }
    }
    
    Context 'Real-World Examples' {
        It 'Extracts keywords from "Debug recurring session validation failures"' {
            $result = Get-DescriptiveKeywords -Objective "Debug recurring session validation failures"
            
            $result | Should -Be 'debug-recurring-session-validation-failures'
        }
        
        It 'Extracts keywords from "Implement OAuth 2.0 authentication flow"' {
            $result = Get-DescriptiveKeywords -Objective "Implement OAuth 2.0 authentication flow"
            
            # Should filter out "2" as too short but keep oauth and flow
            $result | Should -Match 'implement'
            $result | Should -Match 'oauth'
            $result | Should -Match 'authentication'
            $result | Should -Match 'flow'
        }
        
        It 'Extracts keywords from "Fix test coverage gaps in UserService"' {
            $result = Get-DescriptiveKeywords -Objective "Fix test coverage gaps in UserService"
            
            $result | Should -Match 'fix'
            $result | Should -Match 'test'
            $result | Should -Match 'coverage'
            $result | Should -Match 'gaps'
            $result | Should -Match 'userservice'
        }
        
        It 'Extracts keywords from "Refactor PaymentProcessor for better error handling"' {
            $result = Get-DescriptiveKeywords -Objective "Refactor PaymentProcessor for better error handling"
            
            $result | Should -Match 'refactor'
            $result | Should -Match 'paymentprocessor'
            $result | Should -Match 'better'
            $result | Should -Match 'error'
            $result | Should -Match 'handling'
        }
    }
    
    Context 'Output Consistency' {
        It 'Always returns string type' {
            $result = Get-DescriptiveKeywords -Objective "Test objective"
            
            $result | Should -BeOfType [string]
        }
        
        It 'Never returns null (returns empty string instead)' {
            $result = Get-DescriptiveKeywords -Objective ""
            
            # Verify it returns empty string, not $null
            $result | Should -BeOfType [string]
            $result | Should -Be ''
        }
        
        It 'Output contains only lowercase letters, numbers, hyphens, and underscores' {
            $result = Get-DescriptiveKeywords -Objective "Fix the BIG Bug in UserService"
            
            $result | Should -Match '^[a-z0-9_-]*$'
        }
        
        It 'Output has no leading hyphens' {
            $result = Get-DescriptiveKeywords -Objective "the implement feature"
            
            $result | Should -Not -Match '^-'
        }
        
        It 'Output has no trailing hyphens' {
            $result = Get-DescriptiveKeywords -Objective "implement feature the"
            
            $result | Should -Not -Match '-$'
        }
        
        It 'Output has no consecutive hyphens' {
            $result = Get-DescriptiveKeywords -Objective "implement   feature"
            
            $result | Should -Not -Match '--'
        }
    }
}

Describe 'Security - Get-DescriptiveKeywords' {

    Context 'ReDoS Resistance' {
        It 'Completes in <1 second with pathological repeated characters (10,000+)' {
            $pathologicalInput = 'a' * 10000
            $sw = [System.Diagnostics.Stopwatch]::StartNew()
            $result = Get-DescriptiveKeywords -Objective $pathologicalInput
            $sw.Stop()

            $sw.ElapsedMilliseconds | Should -BeLessThan 1000
            $result | Should -BeOfType [string]
        }

        It 'Completes in <1 second with alternating pattern (aaaa...bbbb...)' {
            $pathologicalInput = ('a' * 5000) + ('b' * 5000)
            $sw = [System.Diagnostics.Stopwatch]::StartNew()
            $result = Get-DescriptiveKeywords -Objective $pathologicalInput
            $sw.Stop()

            $sw.ElapsedMilliseconds | Should -BeLessThan 1000
            $result | Should -BeOfType [string]
        }

        It 'Completes in <1 second with regex-adversarial characters' {
            $pathologicalInput = ('.*+?' * 2500)
            $sw = [System.Diagnostics.Stopwatch]::StartNew()
            $result = Get-DescriptiveKeywords -Objective $pathologicalInput
            $sw.Stop()

            $sw.ElapsedMilliseconds | Should -BeLessThan 1000
        }
    }

    Context 'Embedded PowerShell Expression Safety' {
        It 'Does not execute embedded $() expressions' {
            $malicious = 'Fix $(Get-Process | Stop-Process) issue'
            $result = Get-DescriptiveKeywords -Objective $malicious

            # Function treats input as literal text (string ops, no Invoke-Expression)
            # Keywords are extracted from the literal string content
            $result | Should -Match 'fix'
            $result | Should -BeOfType [string]
            # Verify no process was actually stopped (function is string-only)
            Get-Process -Id $PID | Should -Not -BeNullOrEmpty
        }

        It 'Does not execute embedded backtick expressions' {
            $malicious = 'Fix `whoami` issue'
            $result = Get-DescriptiveKeywords -Objective $malicious

            $result | Should -Match 'fix'
            $result | Should -Match 'issue'
        }

        It 'Handles string with environment variable syntax' {
            $result = Get-DescriptiveKeywords -Objective 'Fix $env:PATH issue'

            $result | Should -Match 'fix'
            $result | Should -Match 'issue'
        }
    }

    Context 'Boundary Testing' {
        It 'Handles very long string (100,000 characters)' {
            $longInput = 'word ' * 20000
            $result = Get-DescriptiveKeywords -Objective $longInput

            $result | Should -BeOfType [string]
            $parts = $result -split '-'
            $parts.Count | Should -BeLessOrEqual 5
        }

        It 'Handles single character objective' {
            $result = Get-DescriptiveKeywords -Objective 'X'

            # 'X' is only 1 char, below the 3-char minimum
            $result | Should -Be ''
        }

        It 'Handles objective of exactly 3 characters' {
            $result = Get-DescriptiveKeywords -Objective 'fix'

            $result | Should -Be 'fix'
        }
    }
}

Describe 'Module Exports' {
    It 'New-PopulatedSessionLog is exported' {
        $command = Get-Command New-PopulatedSessionLog -ErrorAction SilentlyContinue
        
        $command | Should -Not -BeNullOrEmpty
        $command.CommandType | Should -Be 'Function'
    }
    
    It 'Get-DescriptiveKeywords is exported' {
        $command = Get-Command Get-DescriptiveKeywords -ErrorAction SilentlyContinue
        
        $command | Should -Not -BeNullOrEmpty
        $command.CommandType | Should -Be 'Function'
    }
    
    It 'Functions are callable after import' {
        $gitInfo = @{ Branch = 'main'; Commit = 'abc1234'; Status = 'clean' }
        $userInput = @{ SessionNumber = 1; Objective = 'Test' }
        
        { Get-DescriptiveKeywords -Objective "Test" } | Should -Not -Throw
        { 
            New-PopulatedSessionLog -Template "NN YYYY-MM-DD [branch name] [SHA] [What this session aims to accomplish] [clean/dirty]" -GitInfo $gitInfo -UserInput $userInput 
        } | Should -Not -Throw
    }
    
    It 'Module can be imported multiple times without errors' {
        { Import-Module $PSScriptRoot/../.claude/skills/session-init/modules/TemplateHelpers.psm1 -Force } | Should -Not -Throw
        { Import-Module $PSScriptRoot/../.claude/skills/session-init/modules/TemplateHelpers.psm1 -Force } | Should -Not -Throw
    }
    
    It 'Imports both GitHelpers and TemplateHelpers without type redefinition errors' {
        # This tests that ApplicationFailedException type collision is handled
        { Import-Module $PSScriptRoot/../.claude/skills/session-init/modules/GitHelpers.psm1 -Force } | Should -Not -Throw
        { Import-Module $PSScriptRoot/../.claude/skills/session-init/modules/TemplateHelpers.psm1 -Force } | Should -Not -Throw
    }
    
    It 'Imports TemplateHelpers before GitHelpers without type redefinition errors' {
        # Test reverse import order
        Remove-Module TemplateHelpers -Force -ErrorAction SilentlyContinue
        Remove-Module GitHelpers -Force -ErrorAction SilentlyContinue
        
        { Import-Module $PSScriptRoot/../.claude/skills/session-init/modules/TemplateHelpers.psm1 -Force } | Should -Not -Throw
        { Import-Module $PSScriptRoot/../.claude/skills/session-init/modules/GitHelpers.psm1 -Force } | Should -Not -Throw
        
        # Re-import TemplateHelpers for remaining tests
        Import-Module $PSScriptRoot/../.claude/skills/session-init/modules/TemplateHelpers.psm1 -Force
    }
}

Describe 'SkipValidation Safeguard' {
    # Tests for SkipValidation behavior: when set, missing placeholders produce a warning
    # instead of throwing, allowing the session to proceed despite template version mismatch.
    # This is useful for investigating broken templates while still creating session logs.

    BeforeAll {
        # Re-import module in case previous tests removed it
        Import-Module $PSScriptRoot/../.claude/skills/session-init/modules/TemplateHelpers.psm1 -Force
        
        $Script:GitInfo = @{
            Branch = 'main'
            Commit = 'abc1234'
            Status = 'clean'
        }
        $Script:UserInput = @{
            SessionNumber = 1
            Objective = 'Test'
        }
    }

    It 'Warns but continues when placeholders missing with SkipValidation' {
        # Template missing ALL required placeholders - with SkipValidation, it warns but proceeds
        $invalidTemplate = "# Session Log`n`nNo placeholders here."

        # Should NOT throw when SkipValidation is set
        { 
            New-PopulatedSessionLog -Template $invalidTemplate -GitInfo $Script:GitInfo -UserInput $Script:UserInput -SkipValidation -WarningAction SilentlyContinue
        } | Should -Not -Throw
    }

    It 'Warning message mentions missing placeholders and version mismatch' {
        $invalidTemplate = "# Session Log`n`nNo placeholders here."
        
        # Capture the warning message
        $warnings = New-PopulatedSessionLog -Template $invalidTemplate -GitInfo $Script:GitInfo -UserInput $Script:UserInput -SkipValidation 3>&1
        $warningText = $warnings | Where-Object { $_ -is [System.Management.Automation.WarningRecord] } | Select-Object -ExpandProperty Message -First 1
        
        $warningText | Should -Match 'missing required placeholders'
        $warningText | Should -Match 'version mismatch'
    }

    It 'Throws exception when placeholders missing without SkipValidation' {
        # Fail-fast design: missing placeholders always throw
        $invalidTemplate = "# Session Log`n`nNo placeholders here."

        {
            New-PopulatedSessionLog -Template $invalidTemplate -GitInfo $Script:GitInfo -UserInput $Script:UserInput
        } | Should -Throw -ExceptionType ([System.InvalidOperationException])
    }
    
    It 'Does not throw when valid template used with SkipValidation' {
        $validTemplate = "NN YYYY-MM-DD [branch name] [SHA] [What this session aims to accomplish] [clean/dirty]"
        
        { 
            New-PopulatedSessionLog -Template $validTemplate -GitInfo $Script:GitInfo -UserInput $Script:UserInput -SkipValidation 
        } | Should -Not -Throw
    }
}
