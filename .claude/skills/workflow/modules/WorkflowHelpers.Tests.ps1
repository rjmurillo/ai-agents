#!/usr/bin/env pwsh
#Requires -Module Pester

<#
.SYNOPSIS
    Pester tests for WorkflowHelpers module.
#>

BeforeAll {
    $ModulePath = Join-Path $PSScriptRoot '../modules/WorkflowHelpers.psm1'
    Import-Module $ModulePath -Force
}

Describe 'Test-MCPAvailability' {
    Context 'When MCP environment variable is set' {
        BeforeEach { $env:AGENT_ORCHESTRATION_MCP_URL = 'http://localhost:3000' }
        AfterEach  { Remove-Item Env:\AGENT_ORCHESTRATION_MCP_URL -ErrorAction SilentlyContinue }

        It 'returns true' {
            Test-MCPAvailability | Should -BeTrue
        }
    }

    Context 'When no MCP indicators present' {
        BeforeEach { Remove-Item Env:\AGENT_ORCHESTRATION_MCP_URL -ErrorAction SilentlyContinue }

        It 'returns false when no config files exist' {
            # Run from a temp dir with no config
            Push-Location (New-Item -ItemType Directory -Path (Join-Path ([System.IO.Path]::GetTempPath()) ([System.IO.Path]::GetRandomFileName())) -Force)
            try {
                Test-MCPAvailability | Should -BeFalse
            }
            finally {
                Pop-Location
            }
        }
    }
}

Describe 'Get-WorkflowContext' {
    Context 'When context file does not exist' {
        It 'returns empty object with expected properties' {
            $ctx = Get-WorkflowContext -WorkflowContextPath 'nonexistent-path.json'
            $ctx.SessionNumber | Should -BeNullOrEmpty
            $ctx.LastCommand   | Should -BeNullOrEmpty
        }
    }

    Context 'When context file exists' {
        BeforeAll {
            $TempFile = Join-Path ([System.IO.Path]::GetTempPath()) 'test-wf-ctx.json'
            @{ SessionNumber = 42; LastCommand = '0-init'; Branch = 'main' } |
                ConvertTo-Json | Set-Content $TempFile
        }
        AfterAll { Remove-Item $TempFile -ErrorAction SilentlyContinue }

        It 'returns parsed context' {
            $ctx = Get-WorkflowContext -WorkflowContextPath $TempFile
            $ctx.SessionNumber | Should -Be 42
            $ctx.LastCommand   | Should -Be '0-init'
        }
    }
}

Describe 'Set-WorkflowContext' {
    It 'writes context to file and sets Timestamp' {
        $TempFile = Join-Path ([System.IO.Path]::GetTempPath()) 'set-wf-ctx.json'
        try {
            $ctx = [PSCustomObject]@{ SessionNumber = 1; LastCommand = 'test' }
            Set-WorkflowContext -Context $ctx -WorkflowContextPath $TempFile
            Test-Path $TempFile | Should -BeTrue
            $read = Get-Content $TempFile -Raw | ConvertFrom-Json
            $read.LastCommand | Should -Be 'test'
            $read.Timestamp   | Should -Not -BeNullOrEmpty
        }
        finally {
            Remove-Item $TempFile -ErrorAction SilentlyContinue
        }
    }
}

Describe 'Invoke-AgentOrchestrationMCP' {
    Context 'When MCP is unavailable' {
        BeforeEach { Remove-Item Env:\AGENT_ORCHESTRATION_MCP_URL -ErrorAction SilentlyContinue }

        It 'returns fallback result' {
            Push-Location (New-Item -ItemType Directory -Path (Join-Path ([System.IO.Path]::GetTempPath()) ([System.IO.Path]::GetRandomFileName())) -Force)
            try {
                $result = Invoke-AgentOrchestrationMCP -ToolName 'invoke_agent' -Arguments @{ agent = 'planner' }
                $result.Fallback  | Should -BeTrue
                $result.Success   | Should -BeFalse
                $result.ToolName  | Should -Be 'invoke_agent'
            }
            finally { Pop-Location }
        }
    }

    Context 'When MCP is available' {
        BeforeEach { $env:AGENT_ORCHESTRATION_MCP_URL = 'http://localhost:3000' }
        AfterEach  { Remove-Item Env:\AGENT_ORCHESTRATION_MCP_URL -ErrorAction SilentlyContinue }

        It 'returns success result' {
            $result = Invoke-AgentOrchestrationMCP -ToolName 'invoke_agent' -Arguments @{ agent = 'planner' }
            $result.Success  | Should -BeTrue
            $result.ToolName | Should -Be 'invoke_agent'
        }
    }
}
