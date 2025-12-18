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
