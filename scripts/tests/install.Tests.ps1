<#
.SYNOPSIS
    Pester tests for install.ps1 unified installer.

.DESCRIPTION
    Tests parameter validation, help content, and basic invocation patterns
    for the unified install script. Does not perform actual installation
    to avoid side effects.

.NOTES
    Requires Pester 5.x or later.
#>

BeforeAll {
    $Script:InstallScript = Join-Path $PSScriptRoot "..\install.ps1"
    $Script:ModulePath = Join-Path $PSScriptRoot "..\lib\Install-Common.psm1"
}

Describe "install.ps1 Script Structure" {
    Context "File Existence" {
        It "Script file exists" {
            Test-Path $Script:InstallScript | Should -Be $true
        }

        It "Module file exists" {
            Test-Path $Script:ModulePath | Should -Be $true
        }
    }

    Context "Help Documentation" {
        It "Has synopsis" {
            $content = Get-Content $Script:InstallScript -Raw
            $content | Should -Match "\.SYNOPSIS"
        }

        It "Has description" {
            $content = Get-Content $Script:InstallScript -Raw
            $content | Should -Match "\.DESCRIPTION"
        }

        It "Has examples" {
            $content = Get-Content $Script:InstallScript -Raw
            $content | Should -Match "\.EXAMPLE"
        }

        It "Documents remote installation example" {
            $content = Get-Content $Script:InstallScript -Raw
            $content | Should -Match "iex"
            $content | Should -Match "DownloadString"
        }
    }
}

Describe "Parameter Definitions" {
    BeforeAll {
        # Parse the script to get parameter information
        $Script:ScriptInfo = Get-Command $Script:InstallScript
    }

    Context "Environment Parameter" {
        It "Has Environment parameter" {
            $Script:ScriptInfo.Parameters.ContainsKey("Environment") | Should -Be $true
        }

        It "Environment accepts Claude, Copilot, VSCode" {
            $param = $Script:ScriptInfo.Parameters["Environment"]
            $validateSet = $param.Attributes | Where-Object { $_ -is [System.Management.Automation.ValidateSetAttribute] }
            $validateSet.ValidValues | Should -Contain "Claude"
            $validateSet.ValidValues | Should -Contain "Copilot"
            $validateSet.ValidValues | Should -Contain "VSCode"
        }
    }

    Context "Global Parameter" {
        It "Has Global switch parameter" {
            $Script:ScriptInfo.Parameters.ContainsKey("Global") | Should -Be $true
            $Script:ScriptInfo.Parameters["Global"].SwitchParameter | Should -Be $true
        }
    }

    Context "RepoPath Parameter" {
        It "Has RepoPath parameter" {
            $Script:ScriptInfo.Parameters.ContainsKey("RepoPath") | Should -Be $true
        }

        It "RepoPath is string type" {
            $Script:ScriptInfo.Parameters["RepoPath"].ParameterType.Name | Should -Be "String"
        }
    }

    Context "Force Parameter" {
        It "Has Force switch parameter" {
            $Script:ScriptInfo.Parameters.ContainsKey("Force") | Should -Be $true
            $Script:ScriptInfo.Parameters["Force"].SwitchParameter | Should -Be $true
        }
    }
}

Describe "Script Content Analysis" {
    BeforeAll {
        $Script:Content = Get-Content $Script:InstallScript -Raw
    }

    Context "Remote Execution Support" {
        It "Detects remote execution context" {
            $Script:Content | Should -Match '\$IsRemoteExecution\s*='
            $Script:Content | Should -Match '\$PSScriptRoot'
        }

        It "Has bootstrap logic for remote execution" {
            $Script:Content | Should -Match "TempDir"
            $Script:Content | Should -Match "WebClient"
            $Script:Content | Should -Match "DownloadFile"
        }

        It "Downloads required files from GitHub" {
            $Script:Content | Should -Match "raw\.githubusercontent\.com"
            $Script:Content | Should -Match "Install-Common\.psm1"
            $Script:Content | Should -Match "Config\.psd1"
        }
    }

    Context "Interactive Mode" {
        It "Has interactive environment selection" {
            $Script:Content | Should -Match "Select Environment"
            $Script:Content | Should -Match "Claude Code"
            $Script:Content | Should -Match "Copilot CLI"
            $Script:Content | Should -Match "VS Code"
        }

        It "Has interactive scope selection" {
            $Script:Content | Should -Match "Select Scope"
            $Script:Content | Should -Match "Global"
            $Script:Content | Should -Match "Repository"
        }
    }

    Context "Module Integration" {
        It "Imports Install-Common module" {
            $Script:Content | Should -Match "Import-Module.*Install-Common"
        }

        It "Uses Get-InstallConfig function" {
            $Script:Content | Should -Match "Get-InstallConfig"
        }

        It "Uses Resolve-DestinationPath function" {
            $Script:Content | Should -Match "Resolve-DestinationPath"
        }

        It "Uses Test-SourceDirectory function" {
            $Script:Content | Should -Match "Test-SourceDirectory"
        }

        It "Uses Get-AgentFiles function" {
            $Script:Content | Should -Match "Get-AgentFiles"
        }

        It "Uses Copy-AgentFile function" {
            $Script:Content | Should -Match "Copy-AgentFile"
        }

        It "Uses Write-InstallHeader function" {
            $Script:Content | Should -Match "Write-InstallHeader"
        }

        It "Uses Write-InstallComplete function" {
            $Script:Content | Should -Match "Write-InstallComplete"
        }
    }

    Context "Repo-Specific Features" {
        It "Validates git repository for Repo scope" {
            $Script:Content | Should -Match "Test-GitRepository"
        }

        It "Creates .agents directories for Repo scope" {
            $Script:Content | Should -Match "Initialize-AgentsDirectories"
        }

        It "Handles instructions file installation" {
            $Script:Content | Should -Match "Install-InstructionsFile"
        }
    }

    Context "Error Handling" {
        It "Sets ErrorActionPreference to Stop" {
            $Script:Content | Should -Match '\$ErrorActionPreference\s*=\s*"Stop"'
        }

        It "Has cleanup for remote execution on error" {
            $Script:Content | Should -Match "Remove-Item.*TempDir.*Recurse.*Force"
        }
    }

    Context "Summary Output" {
        It "Tracks installation statistics" {
            $Script:Content | Should -Match '\$Stats'
            $Script:Content | Should -Match "Installed"
            $Script:Content | Should -Match "Updated"
            $Script:Content | Should -Match "Skipped"
        }

        It "Displays summary at end" {
            $Script:Content | Should -Match "Summary.*installed.*updated.*skipped"
        }
    }
}

Describe "GitHub API Integration (Remote Mode)" {
    BeforeAll {
        $Script:Content = Get-Content $Script:InstallScript -Raw
    }

    Context "API Configuration" {
        It "Uses GitHub API to list files" {
            $Script:Content | Should -Match "api\.github\.com"
        }

        It "Sets User-Agent header" {
            $Script:Content | Should -Match "User-Agent"
        }

        It "Sets Accept header for GitHub API" {
            $Script:Content | Should -Match "application/vnd\.github"
        }
    }

    Context "File Pattern Matching" {
        It "Converts glob pattern to regex for filtering" {
            $Script:Content | Should -Match "PatternRegex"
        }

        It "Filters files by type" {
            $Script:Content | Should -Match 'type\s*-eq\s*"file"'
        }
    }
}
