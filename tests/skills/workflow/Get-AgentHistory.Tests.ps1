#!/usr/bin/env pwsh
#Requires -Module Pester

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot '../../../.claude/skills/workflow/scripts/Get-AgentHistory.ps1'
    $ModulePath = Join-Path $PSScriptRoot '../../../.claude/skills/workflow/modules/WorkflowHelpers.psm1'
    Import-Module $ModulePath -Force
}

Describe 'Get-AgentHistory.ps1' {
    Context 'Syntax validation' {
        It 'has no parse errors' {
            $errors = $null
            $null = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]([System.Management.Automation.Language.ParseError[]]$errors))
            $errors | Should -BeNullOrEmpty
        }

        It 'defines -Limit parameter with default 50' {
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
            $params = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] }, $true)
            $limitParam = $params | Where-Object { $_.Name.VariablePath.UserPath -eq 'Limit' }
            $limitParam | Should -Not -BeNullOrEmpty
        }

        It 'defines -SessionNumber parameter' {
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
            $params = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] }, $true)
            ($params | Where-Object { $_.Name.VariablePath.UserPath -eq 'SessionNumber' }) | Should -Not -BeNullOrEmpty
        }

        It 'defines -AgentName parameter' {
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
            $params = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] }, $true)
            ($params | Where-Object { $_.Name.VariablePath.UserPath -eq 'AgentName' }) | Should -Not -BeNullOrEmpty
        }

        It 'defines -OutputFormat parameter with ValidateSet Json and Table' {
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
            $params = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] }, $true)
            $ofParam = $params | Where-Object { $_.Name.VariablePath.UserPath -eq 'OutputFormat' }
            $ofParam | Should -Not -BeNullOrEmpty
            $validateSet = $ofParam.Attributes | Where-Object { $_.TypeName.Name -eq 'ValidateSet' }
            $validateSet | Should -Not -BeNullOrEmpty
            $positionalArgs = $validateSet.PositionalArguments.Value
            $positionalArgs | Should -Contain 'Json'
            $positionalArgs | Should -Contain 'Table'
        }
    }

    Context 'MCP unavailable (fallback behavior)' {
        It 'exits with code 2 when MCP is unavailable' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "agent-history-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            try {
                & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' 2>&1 | Out-Null
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 2
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'MCP available - Table output (default)' {
        It 'outputs table format header when MCP is configured' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "agent-history-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            # Create a fake mcp config so Test-MCPAvailability returns true
            New-Item -ItemType File -Path (Join-Path $tempDir 'mcp.json') -Value '{}' -Force | Out-Null
            try {
                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' 2>&1
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 0
                ($output -join "`n") | Should -Match 'Agent Invocation History'
                ($output -join "`n") | Should -Match 'Session:.*All'
                ($output -join "`n") | Should -Match 'Agent:.*All'
                ($output -join "`n") | Should -Match 'Limit:.*50'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }

        It 'displays filtered session number in table header' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "agent-history-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            New-Item -ItemType File -Path (Join-Path $tempDir 'mcp.json') -Value '{}' -Force | Out-Null
            try {
                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    & '$ScriptPath' -SessionNumber 42 2>&1
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 0
                ($output -join "`n") | Should -Match 'Session:.*42'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }

        It 'displays filtered agent name in table header' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "agent-history-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            New-Item -ItemType File -Path (Join-Path $tempDir 'mcp.json') -Value '{}' -Force | Out-Null
            try {
                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    & '$ScriptPath' -AgentName planner 2>&1
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 0
                ($output -join "`n") | Should -Match 'Agent:.*planner'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }

        It 'respects custom Limit parameter' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "agent-history-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            New-Item -ItemType File -Path (Join-Path $tempDir 'mcp.json') -Value '{}' -Force | Out-Null
            try {
                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    & '$ScriptPath' -Limit 10 2>&1
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 0
                ($output -join "`n") | Should -Match 'Limit:.*10'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'MCP available - Json output' {
        It 'outputs valid JSON when OutputFormat is Json' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "agent-history-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            New-Item -ItemType File -Path (Join-Path $tempDir 'mcp.json') -Value '{}' -Force | Out-Null
            try {
                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    & '$ScriptPath' -OutputFormat Json 2>&1
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 0
                # Filter warning lines and parse JSON from stdout
                $jsonLines = $output | Where-Object { $_ -notmatch '^WARNING:' -and $_ -match '\S' }
                $jsonText = $jsonLines -join "`n"
                $parsed = $jsonText | ConvertFrom-Json
                $parsed.Limit | Should -Be 50
                $parsed.QueryTime | Should -Not -BeNullOrEmpty
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }

        It 'includes filter values in JSON output' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "agent-history-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            New-Item -ItemType File -Path (Join-Path $tempDir 'mcp.json') -Value '{}' -Force | Out-Null
            try {
                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    & '$ScriptPath' -OutputFormat Json -SessionNumber 5 -AgentName implementer -Limit 25 2>&1
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 0
                $jsonLines = $output | Where-Object { $_ -notmatch '^WARNING:' -and $_ -match '\S' }
                $parsed = ($jsonLines -join "`n") | ConvertFrom-Json
                $parsed.SessionFilter | Should -Be 5
                $parsed.AgentFilter | Should -Be 'implementer'
                $parsed.Limit | Should -Be 25
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }
}
