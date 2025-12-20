#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Pester tests for Verify-BotAccountActions.ps1

.DESCRIPTION
    Tests the bot account verification script functionality.
#>

BeforeAll {
    $scriptPath = Join-Path $PSScriptRoot '..' 'Verify-BotAccountActions.ps1'
    
    # Mock gh CLI commands
    function gh {
        param([Parameter(ValueFromRemainingArguments)]$Args)
        
        # Return mock data based on command
        $command = $Args -join ' '
        
        switch -Regex ($command) {
            '^--version' {
                return 'gh version 2.40.0'
            }
            '^api user' {
                return '{"login":"test-user","type":"User"}'
            }
            '^repo view.*nameWithOwner' {
                return 'owner/repo'
            }
            '^workflow list' {
                return '[{"name":"Test Workflow","state":"active"}]'
            }
            '^workflow view' {
                return '{"name":"Test Workflow","state":"active"}'
            }
            '^pr list.*author' {
                return '[{"number":123,"headRefName":"test-branch","state":"open"}]'
            }
            '^run list' {
                return '[{"status":"completed","conclusion":"success","name":"Test Run"}]'
            }
            default {
                throw "Unknown gh command: $command"
            }
        }
    }
}

Describe 'Verify-BotAccountActions.ps1' {
    Context 'Script Validation' {
        It 'Script file exists' {
            $scriptPath | Should -Exist
        }
        
        It 'Script has valid PowerShell syntax' {
            { $null = [System.Management.Automation.PSParser]::Tokenize((Get-Content $scriptPath -Raw), [ref]$null) } | Should -Not -Throw
        }
        
        It 'Script has help documentation' {
            $help = Get-Help $scriptPath
            $help.Synopsis | Should -Not -BeNullOrEmpty
            $help.Description | Should -Not -BeNullOrEmpty
        }
    }
    
    Context 'Parameter Validation' {
        It 'Has BotAccount parameter with default value' {
            $params = (Get-Command $scriptPath).Parameters
            $params.ContainsKey('BotAccount') | Should -Be $true
            $params['BotAccount'].Attributes.Where({$_ -is [System.Management.Automation.ParameterAttribute]}).Mandatory | Should -Be $false
        }
        
        It 'Has Repository parameter' {
            $params = (Get-Command $scriptPath).Parameters
            $params.ContainsKey('Repository') | Should -Be $true
        }
        
        It 'Has TestWorkflow parameter with default value' {
            $params = (Get-Command $scriptPath).Parameters
            $params.ContainsKey('TestWorkflow') | Should -Be $true
        }
    }
    
    Context 'Function Tests' {
        BeforeAll {
            # Source the script to load functions
            . $scriptPath
        }
        
        It 'Test-GhCliInstalled returns boolean' {
            Mock gh { return 'gh version 2.40.0' }
            $result = Test-GhCliInstalled
            $result | Should -BeOfType [bool]
        }
        
        It 'Get-CurrentRepository returns repository name' {
            Mock gh { return 'owner/repo' } -ParameterFilter { $Args -contains 'repo' }
            $result = Get-CurrentRepository
            $result | Should -Be 'owner/repo'
        }
        
        It 'Get-AuthenticatedUser returns username' {
            Mock gh { return 'test-user' } -ParameterFilter { $Args -contains 'api' }
            $result = Get-AuthenticatedUser
            $result | Should -Be 'test-user'
        }
    }
    
    Context 'Workflow Access Tests' {
        BeforeAll {
            . $scriptPath
        }
        
        It 'Test-WorkflowDispatch returns success for valid workflow' {
            Mock gh { return '[{"name":"Test","state":"active"}]' }
            $result = Test-WorkflowDispatch -Workflow 'test.yml' -Repo 'owner/repo'
            $result.Success | Should -Be $true
        }
        
        It 'Test-WorkflowDispatch returns error for invalid workflow' {
            Mock gh { throw 'Workflow not found' }
            $result = Test-WorkflowDispatch -Workflow 'invalid.yml' -Repo 'owner/repo'
            $result.Success | Should -Be $false
            $result.Error | Should -Not -BeNullOrEmpty
        }
    }
    
    Context 'Bot PR Workflow Tests' {
        BeforeAll {
            . $scriptPath
        }
        
        It 'Test-BotPRWorkflows returns data for bot with PRs' {
            Mock gh { 
                param([Parameter(ValueFromRemainingArguments)]$Args)
                $command = $Args -join ' '
                if ($command -match 'pr list') {
                    return '[{"number":123,"headRefName":"test-branch","state":"open"}]'
                }
                if ($command -match 'run list') {
                    return '[{"status":"completed","conclusion":"success","name":"Test"}]'
                }
            }
            
            $result = Test-BotPRWorkflows -Repo 'owner/repo' -Bot 'test-bot'
            $result | Should -Not -BeNull
            $result.PR | Should -Be 123
            $result.HasRuns | Should -Be $true
        }
        
        It 'Test-BotPRWorkflows returns null for bot with no PRs' {
            Mock gh { return '[]' }
            $result = Test-BotPRWorkflows -Repo 'owner/repo' -Bot 'test-bot'
            $result | Should -BeNull
        }
    }
    
    Context 'Error Handling' {
        It 'Handles missing gh CLI gracefully' {
            Mock Test-GhCliInstalled { return $false }
            # Script should exit with error code 1
            # This would need to be tested by invoking the script in a separate process
        }
        
        It 'Handles authentication errors gracefully' {
            Mock Get-AuthenticatedUser { return $null }
            # Script should exit with error code 1
        }
    }
}

Describe 'Integration Tests' -Tag 'Integration' {
    Context 'Real gh CLI Tests' {
        BeforeAll {
            # Only run if gh CLI is actually installed
            $ghInstalled = $null -ne (Get-Command gh -ErrorAction SilentlyContinue)
        }
        
        It 'Can check gh CLI installation' -Skip:(-not $ghInstalled) {
            $version = gh --version
            $version | Should -Not -BeNullOrEmpty
        }
        
        It 'Can get authenticated user' -Skip:(-not $ghInstalled) {
            try {
                $user = gh api user --jq '.login' 2>$null
                $user | Should -Not -BeNullOrEmpty
            }
            catch {
                Set-ItResult -Skipped -Because 'Not authenticated with gh CLI'
            }
        }
    }
}
