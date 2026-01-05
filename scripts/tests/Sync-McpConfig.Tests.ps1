<#
.SYNOPSIS
    Pester tests for Sync-McpConfig.ps1 script.

.DESCRIPTION
    Tests the MCP configuration synchronization from Claude's .mcp.json
    to VS Code's .vscode/mcp.json format.

.NOTES
    Requires Pester 5.x or later.
#>

BeforeAll {
    $Script:ScriptPath = Join-Path $PSScriptRoot "..\Sync-McpConfig.ps1"
    $Script:TestDir = Join-Path $TestDrive "mcp-test"
}

Describe "Sync-McpConfig.ps1" {
    BeforeEach {
        # Create fresh test directory for each test
        New-Item -ItemType Directory -Path $Script:TestDir -Force | Out-Null
    }

    AfterEach {
        # Clean up test directory
        if (Test-Path $Script:TestDir) {
            Remove-Item -Path $Script:TestDir -Recurse -Force
        }
    }

    Context "Basic Transformation" {
        It "Transforms mcpServers to servers key" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            $sourceContent = @{
                mcpServers = @{
                    testServer = @{
                        type = "stdio"
                        command = "test"
                    }
                }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath

            # Assert
            $destPath | Should -Exist
            $destJson = Get-Content -Path $destPath -Raw | ConvertFrom-Json
            $destJson.servers | Should -Not -BeNullOrEmpty
            $destJson.servers.testServer | Should -Not -BeNullOrEmpty
            $destJson.servers.testServer.type | Should -Be "stdio"
            $destJson.servers.testServer.command | Should -Be "test"
        }

        It "Preserves all server properties" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            $sourceContent = @{
                mcpServers = @{
                    serena = @{
                        type = "stdio"
                        command = "uvx"
                        args = @("--from", "git+https://example.com", "serena")
                    }
                    deepwiki = @{
                        type = "http"
                        url = "https://example.com/mcp"
                    }
                }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath

            # Assert
            $destJson = Get-Content -Path $destPath -Raw | ConvertFrom-Json
            $destJson.servers.serena.args | Should -HaveCount 3
            $destJson.servers.deepwiki.url | Should -Be "https://example.com/mcp"
        }

        It "Preserves additional top-level keys like inputs" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            $sourceContent = @{
                mcpServers = @{
                    test = @{ type = "stdio"; command = "test" }
                }
                inputs = @(
                    @{
                        type = "promptString"
                        id = "api-key"
                        description = "API Key"
                    }
                )
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath

            # Assert
            $destJson = Get-Content -Path $destPath -Raw | ConvertFrom-Json
            $destJson.inputs | Should -Not -BeNullOrEmpty
            $destJson.inputs[0].id | Should -Be "api-key"
        }
    }

    Context "Error Handling" {
        It "Fails when source file does not exist" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir "nonexistent.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"

            # Act & Assert
            { & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath -ErrorAction Stop } |
                Should -Throw "*not found*"
        }

        It "Fails when source is missing mcpServers key" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            $sourceContent = @{
                servers = @{ test = @{ type = "stdio" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act & Assert
            { & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath -ErrorAction Stop } |
                Should -Throw "*mcpServers*"
        }

        It "Fails when source has invalid JSON" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            Set-Content -Path $sourcePath -Value "{ invalid json }" -Encoding UTF8

            # Act & Assert
            { & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath -ErrorAction Stop } |
                Should -Throw
        }
    }

    Context "Idempotency" {
        It "Does not rewrite file when content is identical" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # First sync
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath
            $firstWriteTime = (Get-Item $destPath).LastWriteTime

            # Small delay to ensure timestamp would differ if file was rewritten
            Start-Sleep -Milliseconds 100

            # Act - Second sync
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath
            $secondWriteTime = (Get-Item $destPath).LastWriteTime

            # Assert - File should not have been rewritten
            $secondWriteTime | Should -Be $firstWriteTime
        }

        It "Rewrites file when Force is specified even if identical" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # First sync
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath
            $firstWriteTime = (Get-Item $destPath).LastWriteTime

            # Small delay
            Start-Sleep -Milliseconds 100

            # Act - Second sync with Force
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath -Force
            $secondWriteTime = (Get-Item $destPath).LastWriteTime

            # Assert - File should have been rewritten
            $secondWriteTime | Should -BeGreaterThan $firstWriteTime
        }

        It "Returns false with PassThru when files already in sync" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # First sync
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath

            # Act - Second sync with PassThru
            $result = & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath -PassThru

            # Assert - Should return false since files are already in sync
            $result | Should -Be $false
        }

        It "Returns true with PassThru when files are synced" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act - First sync with PassThru
            $result = & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath -PassThru

            # Assert - Should return true since files were synced
            $result | Should -Be $true
        }
    }

    Context "WhatIf Support" {
        It "Does not create file when WhatIf is specified" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath -WhatIf

            # Assert
            $destPath | Should -Not -Exist
        }

        It "Returns false when WhatIf is used with PassThru" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act
            $result = & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath -WhatIf -PassThru

            # Assert
            $result | Should -Be $false
            $destPath | Should -Not -Exist
        }
    }

    Context "PassThru Behavior" {
        It "Returns true when file is synced" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act
            $result = & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath -PassThru

            # Assert
            $result | Should -Be $true
        }

        It "Returns false when files already in sync" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # First sync
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath

            # Act - Second sync
            $result = & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath -PassThru

            # Assert
            $result | Should -Be $false
        }
    }

    Context "Serena Transformation" {
        It "Transforms serena context from claude-code to ide" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            $sourceContent = @{
                mcpServers = @{
                    serena = @{
                        type = "stdio"
                        command = "uvx"
                        args = @("--from", "serena-mcp", "serena", "--context", "claude-code")
                    }
                }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath

            # Assert
            $destJson = Get-Content -Path $destPath -Raw | ConvertFrom-Json
            $destJson.servers.serena.args | Should -Contain "ide"
            $destJson.servers.serena.args | Should -Not -Contain "claude-code"
        }

        It "Transforms serena port from 24282 to 24283" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            $sourceContent = @{
                mcpServers = @{
                    serena = @{
                        type = "stdio"
                        command = "uvx"
                        args = @("--port", "24282", "serena")
                    }
                }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath

            # Assert
            $destJson = Get-Content -Path $destPath -Raw | ConvertFrom-Json
            $destJson.servers.serena.args | Should -Contain "24283"
            $destJson.servers.serena.args | Should -Not -Contain "24282"
        }

        It "Transforms both context and port in serena config" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            $sourceContent = @{
                mcpServers = @{
                    serena = @{
                        type = "stdio"
                        command = "uvx"
                        args = @("--from", "serena-mcp", "serena", "--context", "claude-code", "--port", "24282")
                    }
                }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath

            # Assert
            $destJson = Get-Content -Path $destPath -Raw | ConvertFrom-Json
            $destJson.servers.serena.args | Should -Contain "ide"
            $destJson.servers.serena.args | Should -Contain "24283"
            $destJson.servers.serena.args | Should -Not -Contain "claude-code"
            $destJson.servers.serena.args | Should -Not -Contain "24282"
        }

        It "Preserves other serena args unchanged" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            $sourceContent = @{
                mcpServers = @{
                    serena = @{
                        type = "stdio"
                        command = "uvx"
                        args = @("--from", "git+https://github.com/example/serena-mcp", "serena", "--context", "claude-code", "--verbose")
                    }
                }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath

            # Assert
            $destJson = Get-Content -Path $destPath -Raw | ConvertFrom-Json
            $destJson.servers.serena.args | Should -Contain "--from"
            $destJson.servers.serena.args | Should -Contain "git+https://github.com/example/serena-mcp"
            $destJson.servers.serena.args | Should -Contain "serena"
            $destJson.servers.serena.args | Should -Contain "--verbose"
        }

        It "Does not modify non-serena servers" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            $sourceContent = @{
                mcpServers = @{
                    serena = @{
                        type = "stdio"
                        command = "uvx"
                        args = @("--context", "claude-code")
                    }
                    other = @{
                        type = "stdio"
                        command = "node"
                        args = @("--context", "claude-code", "--port", "24282")
                    }
                }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath

            # Assert
            $destJson = Get-Content -Path $destPath -Raw | ConvertFrom-Json
            # Serena should be transformed
            $destJson.servers.serena.args | Should -Contain "ide"
            # Other server should NOT be transformed
            $destJson.servers.other.args | Should -Contain "claude-code"
            $destJson.servers.other.args | Should -Contain "24282"
        }

        It "Handles serena config without args gracefully" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            $sourceContent = @{
                mcpServers = @{
                    serena = @{
                        type = "http"
                        url = "http://localhost:24282"
                    }
                }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath

            # Assert - Should not throw and should preserve config
            $destJson = Get-Content -Path $destPath -Raw | ConvertFrom-Json
            $destJson.servers.serena.type | Should -Be "http"
            $destJson.servers.serena.url | Should -Be "http://localhost:24282"
        }

        It "Does not modify source config (deep clone)" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            $sourceContent = @{
                mcpServers = @{
                    serena = @{
                        type = "stdio"
                        command = "uvx"
                        args = @("--context", "claude-code", "--port", "24282")
                    }
                }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath

            # Assert - Source file should be unchanged
            $sourceJson = Get-Content -Path $sourcePath -Raw | ConvertFrom-Json
            $sourceJson.mcpServers.serena.args | Should -Contain "claude-code"
            $sourceJson.mcpServers.serena.args | Should -Contain "24282"
        }
    }

    Context "Output Format" {
        It "Produces valid JSON output" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath

            # Assert - Should parse without error
            { Get-Content -Path $destPath -Raw | ConvertFrom-Json } | Should -Not -Throw
        }

        It "Output has trailing newline" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath

            # Assert
            $content = [System.IO.File]::ReadAllText($destPath)
            $content | Should -Match "`n$"
        }
    }
}

Describe "Directory Creation" {
    BeforeEach {
        # Create fresh test directory for each test
        $Script:TestDir = Join-Path $TestDrive "mcp-test-$(Get-Random)"
        New-Item -ItemType Directory -Path $Script:TestDir -Force | Out-Null
    }

    AfterEach {
        # Clean up test directory
        if (Test-Path $Script:TestDir) {
            Remove-Item -Path $Script:TestDir -Recurse -Force
        }
    }

    Context "Target Directory Handling" {
        It "Creates .vscode directory if it does not exist" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $vscodePath = Join-Path $Script:TestDir ".vscode"
            $destPath = Join-Path $vscodePath "mcp.json"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Verify .vscode doesn't exist
            $vscodePath | Should -Not -Exist

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath

            # Assert
            $vscodePath | Should -Exist
            $destPath | Should -Exist
        }

        It "Works when .vscode directory already exists" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $vscodePath = Join-Path $Script:TestDir ".vscode"
            $destPath = Join-Path $vscodePath "mcp.json"
            New-Item -ItemType Directory -Path $vscodePath -Force | Out-Null
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath

            # Assert
            $destPath | Should -Exist
        }
    }
}

Describe "Format Compatibility" {
    BeforeAll {
        $gitRoot = git rev-parse --show-toplevel 2>$null
        if ($LASTEXITCODE -eq 0 -and $gitRoot) {
            $Script:RepoRoot = $gitRoot
        } else {
            $Script:RepoRoot = $PWD.Path
        }
        $Script:ClaudeMcpPath = Join-Path $Script:RepoRoot ".mcp.json"
        $Script:VSCodeDir = Join-Path $Script:RepoRoot ".vscode"
        $Script:VSCodeMcpPath = Join-Path $Script:VSCodeDir "mcp.json"
        $Script:HasClaudeMcp = Test-Path $Script:ClaudeMcpPath
        $Script:HasVSCodeMcp = Test-Path $Script:VSCodeMcpPath
    }

    Context "Real Files in Repository" -Skip:(-not $Script:HasClaudeMcp) {
        It "Claude .mcp.json has mcpServers key" {
            $json = Get-Content -Path $Script:ClaudeMcpPath -Raw | ConvertFrom-Json
            $json.mcpServers | Should -Not -BeNullOrEmpty
        }

        It "VS Code .vscode/mcp.json has servers key" -Skip:(-not $Script:HasVSCodeMcp) {
            $json = Get-Content -Path $Script:VSCodeMcpPath -Raw | ConvertFrom-Json
            $json.servers | Should -Not -BeNullOrEmpty
        }

        It "Both files have matching server definitions" -Skip:(-not ($Script:HasClaudeMcp -and $Script:HasVSCodeMcp)) {
            $claudeJson = Get-Content -Path $Script:ClaudeMcpPath -Raw | ConvertFrom-Json -AsHashtable
            $vscodeJson = Get-Content -Path $Script:VSCodeMcpPath -Raw | ConvertFrom-Json -AsHashtable

            $claudeServers = $claudeJson['mcpServers'].Keys | Sort-Object
            $vscodeServers = $vscodeJson['servers'].Keys | Sort-Object

            $claudeServers | Should -Be $vscodeServers
        }
    }
}

Describe "Factory Target Support" {
    BeforeEach {
        # Create fresh test directory for each test
        New-Item -ItemType Directory -Path $Script:TestDir -Force | Out-Null
    }

    AfterEach {
        # Clean up test directory
        if (Test-Path $Script:TestDir) {
            Remove-Item -Path $Script:TestDir -Recurse -Force
        }
    }

    Context "-Target Factory Parameter" {
        It "Uses mcpServers root key for Factory target" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            $sourceContent = @{
                mcpServers = @{
                    testServer = @{
                        type = "stdio"
                        command = "test"
                        args = @("--arg1", "--arg2")
                    }
                }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath -Target factory

            # Assert
            $destPath | Should -Exist
            $destJson = Get-Content -Path $destPath -Raw | ConvertFrom-Json
            $destJson.mcpServers | Should -Not -BeNullOrEmpty
            $destJson.servers | Should -BeNullOrEmpty
            $destJson.mcpServers.testServer.type | Should -Be "stdio"
            $destJson.mcpServers.testServer.command | Should -Be "test"
        }

        It "Does not transform serena config for Factory target" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            $sourceContent = @{
                mcpServers = @{
                    serena = @{
                        type = "stdio"
                        command = "uvx"
                        args = @("--from", "git+https://github.com/oraios/serena", "serena", "start-mcp-server", "--project", "/project", "--context", "claude-code", "--port", "24282")
                    }
                }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath -Target factory

            # Assert
            $destJson = Get-Content -Path $destPath -Raw | ConvertFrom-Json
            $destJson.mcpServers.serena.args | Should -Contain "claude-code"
            $destJson.mcpServers.serena.args | Should -Contain "24282"
        }

        It "Deep clones mcpServers for Factory target" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            $sourceContent = @{
                mcpServers = @{
                    test = @{ type = "stdio" }
                }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath -Target factory

            # Assert
            # Both source and dest should exist and have same content structure
            $sourceJson = Get-Content -Path $sourcePath -Raw | ConvertFrom-Json -AsHashtable
            $destJson = Get-Content -Path $destPath -Raw | ConvertFrom-Json -AsHashtable
            
            # Dest should be a clone (different object) with same content
            $destJson.mcpServers | Should -BeDeepCloneOf $sourceJson.mcpServers
        }

        It "Creates .factory directory when using Factory target" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $factoryPath = Join-Path $Script:TestDir ".factory"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Verify .factory doesn't exist
            $factoryPath | Should -Not -Exist

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath (Join-Path $factoryPath "mcp.json") -Target factory

            # Assert
            $factoryPath | Should -Exist
            Test-Path (Join-Path $factoryPath "mcp.json") | Should -Exist
        }
    }

    Context "Target Parameter Behavior" {
        It "Defaults to vscode when Target not specified" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $vscodePath = Join-Path $Script:TestDir ".vscode"
            $destPath = Join-Path $vscodePath "mcp.json"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Verify .vscode doesn't exist
            $vscodePath | Should -Not -Exist

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath

            # Assert - Should have created VS Code config (servers key)
            $vscodePath | Should -Exist
            $destJson = Get-Content -Path $destPath -Raw | ConvertFrom-Json
            $destJson.servers | Should -Not -BeNullOrEmpty
            $destJson.mcpServers | Should -BeNullOrEmpty
        }

        It "Creates VS Code format when Target is explicitly vscode" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $vscodePath = Join-Path $Script:TestDir ".vscode"
            $destPath = Join-Path $vscodePath "mcp.json"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath -Target vscode

            # Assert
            $destJson = Get-Content -Path $destPath -Raw | ConvertFrom-Json
            $destJson.servers | Should -Not -BeNullOrEmpty
        }

        It "Creates Factory format when Target is explicitly factory" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $factoryPath = Join-Path $Script:TestDir ".factory"
            $destPath = Join-Path $factoryPath "mcp.json"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath -Target factory

            # Assert
            $destJson = Get-Content -Path $destPath -Raw | ConvertFrom-Json
            $destJson.mcpServers | Should -Not -BeNullOrEmpty
            $destJson.servers | Should -BeNullOrEmpty
        }
    }
}

Describe "SyncAll Parameter" {
    BeforeEach {
        # Create fresh test directory for each test
        New-Item -ItemType Directory -Path $Script:TestDir -Force | Out-Null
    }

    AfterEach {
        # Clean up test directory
        if (Test-Path $Script:TestDir) {
            Remove-Item -Path $Script:TestDir -Recurse -Force
        }
    }

    Context "Basic SyncAll Functionality" {
        It "Generates both Factory and VS Code configs" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $factoryPath = Join-Path $Script:TestDir ".factory"
            $vscodePath = Join-Path $Script:TestDir ".vscode"
            $sourceContent = @{
                mcpServers = @{
                    test = @{ type = "stdio"; command = "test" }
                }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Verify directories don't exist
            $factoryPath | Should -Not -Exist
            $vscodePath | Should -Not -Exist

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -SyncAll -Force -RepoRootOverride $Script:TestDir

            # Assert
            $factoryPath | Should -Exist
            $vscodePath | Should -Exist
            
            # Verify Factory format (mcpServers key)
            $factoryJson = Get-Content -Path (Join-Path $factoryPath "mcp.json") -Raw | ConvertFrom-Json
            $factoryJson.mcpServers | Should -Not -BeNullOrEmpty
            $factoryJson.servers | Should -BeNullOrEmpty

            # Verify VS Code format (servers key)
            $vscodeJson = Get-Content -Path (Join-Path $vscodePath "mcp.json") -Raw | ConvertFrom-Json
            $vscodeJson.servers | Should -Not -BeNullOrEmpty
            $vscodeJson.mcpServers | Should -BeNullOrEmpty
        }

        It "Preserves serena transformation in VS Code output" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $sourceContent = @{
                mcpServers = @{
                    serena = @{
                        type = "stdio"
                        command = "uvx"
                        args = @("--from", "serena", "serena", "--context", "claude-code", "--port", "24282")
                    }
                }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -SyncAll -Force -RepoRootOverride $Script:TestDir

            # Assert
            $vscodeJson = Get-Content -Path (Join-Path $Script:TestDir ".vscode/mcp.json") -Raw | ConvertFrom-Json
            $vscodeJson.servers.serena.args | Should -Contain "ide"
            $vscodeJson.servers.serena.args | Should -Contain "24283"
            $vscodeJson.servers.serena.args | Should -Not -Contain "claude-code"
            $vscodeJson.servers.serena.args | Should -Not -Contain "24282"

            $factoryJson = Get-Content -Path (Join-Path $Script:TestDir ".factory/mcp.json") -Raw | ConvertFrom-Json
            $factoryJson.mcpServers.serena.args | Should -Contain "claude-code"
            $factoryJson.mcpServers.serena.args | Should -Contain "24282"
        }

        It "Creates both directories if they don't exist" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Verify directories don't exist
            $factoryPath = Join-Path $Script:TestDir ".factory"
            $vscodePath = Join-Path $Script:TestDir ".vscode"
            $factoryPath | Should -Not -Exist
            $vscodePath | Should -Not -Exist

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -SyncAll -Force -RepoRootOverride $Script:TestDir

            # Assert
            $factoryPath | Should -Exist
            $vscodePath | Should -Exist
        }
    }

    Context "SyncAll with PassThru" {
        It "Returns true when both configs are synced" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act
            $result = & $Script:ScriptPath -SourcePath $sourcePath -SyncAll -RepoRootOverride $Script:TestDir -PassThru

            # Assert
            $result | Should -Be $true
        }

        It "Returns false when both configs already in sync" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # First sync (creates files)
            & $Script:ScriptPath -SourcePath $sourcePath -SyncAll -RepoRootOverride $Script:TestDir

            # Act - Second sync (no changes)
            $result = & $Script:ScriptPath -SourcePath $sourcePath -SyncAll -RepoRootOverride $Script:TestDir -PassThru

            # Assert - Should return false since files are already in sync
            $result | Should -Be $false
        }

        It "Returns true when Force is specified even if in sync" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # First sync
            & $Script:ScriptPath -SourcePath $sourcePath -SyncAll -RepoRootOverride $Script:TestDir

            # Capture write time
            $fcWriteTime = (Get-Item (Join-Path $Script:TestDir ".factory/mcp.json")).LastWriteTime

            # Act - SyncAll with Force
            $result = & $Script:ScriptPath -SourcePath $sourcePath -SyncAll -Force -RepoRootOverride $Script:TestDir -PassThru

            # Assert - Returns true even though no actual changes
            $result | Should -Be $true

            # Verify files were rewritten (timestamps should differ)
            $fcWriteTime2 = (Get-Item (Join-Path $Script:TestDir ".factory/mcp.json")).LastWriteTime
            $fcWriteTime2 | Should -BeGreaterThan $fcWriteTime
        }

        It "Returns true when only Factory needs sync" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $factoryPath = Join-Path $Script:TestDir ".factory"
            $vscodePath = Join-Path $Script:TestDir ".vscode"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Create VS Code file first (manually)
            $vscodeDir = Join-Path $Script:TestDir ".vscode"
            New-Item -ItemType Directory -Path $vscodeDir -Force | Out-Null
            $vscodeJson = @{
                servers = @{
                    test = @{ type = "http"; url = "http://example.com/mcp" }
                }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path (Join-Path $vscodePath "mcp.json") -Value $vscodeJson -Encoding utf8

            # Factory file doesn't exist yet
            Test-Path $factoryPath | Should -Not -Exist

            # Act
            $result = & $Script:ScriptPath -SourcePath $sourcePath -SyncAll -RepoRootOverride $Script:TestDir -PassThru

            # Assert - Only Factory needed sync (but we don't track which)
            $result | Should -Be $true
            $factoryPath | Should -Exist
            Test-Path (Join-Path $factoryPath "mcp.json") | Should -Exist
        }
    }

    Context "SyncAll WhatIf" {
        It "Does not create files when WhatIf is specified" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -SyncAll -RepoRootOverride $Script:TestDir -WhatIf

            # Assert
            $factoryPath = Join-Path $Script:TestDir ".factory"
            $vscodePath = Join-Path $Script:TestDir ".vscode"
            Test-Path $factoryPath | Should -Not -Exist
            Test-Path $vscodePath | Should -Not -Exist
        }

        It "Returns false when WhatIf is used with PassThru" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act
            $result = & $Script:ScriptPath -SourcePath $sourcePath -SyncAll -RepoRootOverride $Script:TestDir -WhatIf -PassThru

            # Assert
            $result | Should -Be $false
        }
    }
}

Describe "Parameter Validation" {
    BeforeEach {
        # Create fresh test directory for each test
        New-Item -ItemType Directory -Path $Script:TestDir -Force | Out-Null
    }

    AfterEach {
        # Clean up test directory
        if (Test-Path $Script:TestDir) {
            Remove-Item -Path $Script:TestDir -Recurse -Force
        }
    }

    Context "SyncAll and DestinationPath Validation" {
        It "Fails when SyncAll and DestinationPath are both specified" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act & Assert
            { & $Script:ScriptPath -SourcePath $sourcePath -SyncAll -DestinationPath $destPath -ErrorAction Stop } |
                Should -Throw "*mutually exclusive*"
        }
    }

    Context "SyncAll and Target Validation" {
        It "Fails when SyncAll and Target are both specified" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act & Assert
            { & $Script:ScriptPath -SourcePath $sourcePath -SyncAll -Target factory -ErrorAction Stop } |
                Should -Throw "*Cannot use SyncAll with Target*"
        }

        It "Fails when SyncAll and Target vscode are both specified" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act & Assert
            { & $Script:ScriptPath -SourcePath $sourcePath -SyncAll -Target vscode -ErrorAction Stop } |
                Should -Throw "*Cannot use SyncAll with Target*"
        }
    }

    Context "Target Parameter Validation" {
        It "Accepts Target factory" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir ".factory"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act & Assert - Should not throw
            { & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath -Target factory -ErrorAction Stop } |
                Should -Not -Throw
        }

        It "Accepts Target vscode" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir ".vscode"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act & Assert - Should not throw
            { & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath -Target vscode -ErrorAction Stop } |
                Should -Not -Throw
        }

        It "Rejects invalid Target value" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir ".vscode"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act & Assert
            { & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath -Target invalid -ErrorAction Stop } |
                Should -Throw "*ValidateSet*"
        }
    }
}

Describe "Get-ChildItem -Force Fix for Hidden Files" {
    BeforeEach {
        # Create fresh test directory for each test
        New-Item -ItemType Directory -Path $Script:TestDir -Force | Out-Null
    }

    AfterEach {
        # Clean up test directory
        if (Test-Path $Script:TestDir) {
            Remove-Item -Path $Script:TestDir -Recurse -Force
        }
    }

    Context "Hidden File Handling" {
        It "Rejects symlinks in source file for security" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            
            # Create a symlink (on platforms that support it)
            try {
                New-Item -ItemType SymbolicLink -Path $sourcePath -Target (Join-Path $Script:TestDir "mcp-target.json") -ErrorAction SilentlyContinue
            } catch {
                # Symlinks not supported on this platform - skip test
                return
            }

            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act & Assert
            { & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath -Target factory -ErrorAction Stop } |
                Should -Throw "*symlink*"
        }

        It "Rejects symlinks in destination file for security" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            $symLinkPath = Join-Path $Script:TestDir "mcp-link.json"
            
            # Create a symlink (on platforms that support it)
            try {
                New-Item -ItemType SymbolicLink -Path $symLinkPath -Target (Join-Path $Script:TestDir "mcp-target.json") -ErrorAction SilentlyContinue
            } catch {
                # Symlinks not supported on this platform - skip test
                return
            }

            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Act & Assert
            { & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $symLinkPath -Target factory -ErrorAction Stop } |
                Should -Throw "*symlink*"
        }

        It "Handles hidden source file correctly" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $destPath = Join-Path $Script:TestDir "mcp.json"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Verify source file is hidden
            $sourceFile = Get-ChildItem -Path $sourcePath -Force | Select-Object -First 1
            $sourceFile.Attributes -bor [System.IO.FileAttributes]::Hidden | Should -Be $true

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $destPath -Target factory

            # Assert - Should process without throwing on hidden file
            $destPath | Should -Exist
            $destJson = Get-Content -Path $destPath -Raw | ConvertFrom-Json
            $destJson.mcpServers.test.type | Should -Be "stdio"
        }

        It "Handles hidden destination file correctly" {
            # Arrange
            $sourcePath = Join-Path $Script:TestDir ".mcp.json"
            $hiddenDir = Join-Path $Script:TestDir ".factory"
            $hiddenPath = Join-Path $hiddenDir "mcp.json"
            $sourceContent = @{
                mcpServers = @{ test = @{ type = "stdio"; command = "test" } }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path $sourcePath -Value $sourceContent -Encoding UTF8

            # Verify destination directory doesn't exist yet
            $hiddenDir | Should -Not -Exist

            # Act
            & $Script:ScriptPath -SourcePath $sourcePath -DestinationPath $hiddenPath -Target factory

            # Assert
            $hiddenPath | Should -Exist
            $hiddenDir | Should -Exist
            $destJson = Get-Content -Path $hiddenPath -Raw | ConvertFrom-Json
            $destJson.mcpServers.test.type | Should -Be "stdio"
        }
    }
}

Describe "Format Compatibility - Factory Format" {
    BeforeAll {
        $gitRoot = git rev-parse --show-toplevel 2>$null
        if ($LASTEXITCODE -eq 0 -and $gitRoot) {
            $Script:RepoRoot = $gitRoot
        } else {
            $Script:RepoRoot = $PWD.Path
        }
        $Script:ClaudeMcpPath = Join-Path $Script:RepoRoot ".mcp.json"
        $Script:VSCodeDir = Join-Path $Script:RepoRoot ".vscode"
        $Script:VSCodeMcpPath = Join-Path $Script:VSCodeDir "mcp.json"
        $Script:FactoryPath = Join-Path $Script:RepoRoot ".factory"
        $Script:FactoryMcpPath = Join-Path $Script:FactoryPath "mcp.json"
        $Script:HasClaudeMcp = Test-Path $Script:ClaudeMcpPath
        $Script:HasVSCodeMcp = Test-Path $Script:VSCodeMcpPath
        $Script:HasFactoryMcp = Test-Path $Script:FactoryMcpPath
    }

    Context "Real Files in Repository" -Skip:(-not $Script:HasClaudeMcp) {
    It "Factory .factory/mcp.json has mcpServers key" {
        $json = Get-Content -Path $Script:FactoryMcpPath -Raw | ConvertFrom-Json
        $json.mcpServers | Should -Not -BeNullOrEmpty
    }
}

Context "Factory Format Compatibility" -Skip:(-not $Script:HasClaudeMcp) {
        It "Factory .factory/mcp.json matches Claude .mcp.json structure" {
            $claudeJson = Get-Content -Path $Script:ClaudeMcpPath -Raw | ConvertFrom-Json -AsHashtable
            $factoryJson = Get-Content -Path $Script:FactoryMcpPath -Raw | ConvertFrom-Json -AsHashtable

            # Both should have mcpServers key
            $claudeJson.mcpServers | Should -Not -BeNullOrEmpty
            $factoryJson.mcpServers | Should -Not -BeNullOrEmpty

            # Server names should match
            $claudeServers = $claudeJson.mcpServers.Keys | Sort-Object
            $factoryServers = $factoryJson.mcpServers.Keys | Sort-Object
            $claudeServers | Should -Be $factoryServers

            # Content should be identical (deep comparison)
            foreach ($server in $claudeServers) {
                $claudeContent = $claudeJson.mcpServers.$server | ConvertTo-Json -Depth 10 -Compress
                $factoryContent = $factoryJson.mcpServers.$server | ConvertTo-Json -Depth 10 -Compress
                $factoryContent | Should -Be $claudeContent
            }
        }
    }

    Context "Three-Way Compatibility" -Skip:(-not ($Script:HasClaudeMcp -and $Script:HasVSCodeMcp -and $Script:HasFactoryMcp)) {
        It "All three formats have matching server definitions" {
            $claudeJson = Get-Content -Path $Script:ClaudeMcpPath -Raw | ConvertFrom-Json -AsHashtable
            $vscodeJson = Get-Content -Path $Script:VSCodeMcpPath -Raw | ConvertFrom-Json -AsHashtable
            $factoryJson = Get-Content -Path $Script:FactoryMcpPath -Raw | ConvertFrom-Json -AsHashtable

            # Get server names from all three sources
            $claudeServers = $claudeJson.mcpServers.Keys | Sort-Object
            $vscodeServers = $vscodeJson.servers.Keys | Sort-Object
            $factoryServers = $factoryJson.mcpServers.Keys | Sort-Object

            # Claude and Factory should have identical structure (both use mcpServers key)
            $claudeServers | Should -Be $factoryServers
            $factoryServers | Should -Be $claudeServers

            # VS Code has different key but same count
            $vscodeServers | Should -HaveCount $claudeServers.Count

            # VS Code has transformed serena if present
            if ($claudeServers.Contains("serena")) {
                $vscodeServers | Should -Contain "serena"
            }
        }

        It "VS Code and Factory can both coexist" {
            $vscodePath = $Script:VSCodeMcpPath
            $factoryPath = $Script:FactoryMcpPath

            # Both files should exist
            Test-Path $vscodePath | Should -Exist
            Test-Path $factoryPath | Should -Exist

            # Each should be valid JSON
            { Get-Content -Path $vscodePath -Raw | ConvertFrom-Json } | Should -Not -Throw
            { Get-Content -Path $factoryPath -Raw | ConvertFrom-Json } | Should -Not -Throw
        }
    }
}
