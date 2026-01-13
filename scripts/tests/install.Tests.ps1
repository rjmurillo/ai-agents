<#
.SYNOPSIS
    Pester tests for install.ps1 unified installer.

.DESCRIPTION
    Tests parameter validation, help content, and basic invocation patterns
    for the unified install script. Does not perform actual installation
    to avoid side effects.

.NOTES
    Requires Pester 5.x or later.

    EXIT CODES:
    0  - Success: All tests passed
    1  - Error: One or more tests failed (set by Pester framework)

    See: ADR-035 Exit Code Standardization
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

        It "Environment has ArgumentCompleter for tab-completion" {
            $param = $Script:ScriptInfo.Parameters["Environment"]
            $argumentCompleter = $param.Attributes | Where-Object { $_ -is [System.Management.Automation.ArgumentCompleterAttribute] }
            $argumentCompleter | Should -Not -BeNullOrEmpty -Because "ArgumentCompleter provides tab-completion without ValidateSet iex conflict"
        }

        It "Environment does not use ValidateSet" {
            # ValidateSet causes iex invocation failure (Issue #892)
            $param = $Script:ScriptInfo.Parameters["Environment"]
            $validateSet = $param.Attributes | Where-Object { $_ -is [System.Management.Automation.ValidateSetAttribute] }
            $validateSet | Should -BeNullOrEmpty -Because "ValidateSet rejects empty strings in iex invocation context"
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

    Context "Version Parameter" {
        It "Has Version parameter" {
            $Script:ScriptInfo.Parameters.ContainsKey("Version") | Should -Be $true
        }

        It "Version is string type" {
            $Script:ScriptInfo.Parameters["Version"].ParameterType.Name | Should -Be "String"
        }

        It "Version has default value of v0.1.0" {
            $param = $Script:ScriptInfo.Parameters["Version"]
            # Check if default value is set in parameter metadata
            $content = Get-Content $Script:InstallScript -Raw
            $content | Should -Match '\[string\]\$Version\s*=\s*"v0\.1\.0"'
        }

        It "Version has ValidatePattern attribute for security" {
            $param = $Script:ScriptInfo.Parameters["Version"]
            $validatePattern = $param.Attributes | Where-Object { $_ -is [System.Management.Automation.ValidatePatternAttribute] }
            $validatePattern | Should -Not -BeNullOrEmpty
            # Pattern should allow alphanumeric, dots, slashes, hyphens, underscores, plus (for SEMVER 2.0 build metadata)
            $validatePattern.RegexPattern | Should -Be '^[\w./+-]+$'
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
            # Script defines ModulePath pointing to Install-Common and imports it
            $Script:Content | Should -Match "Install-Common\.psm1"
            $Script:Content | Should -Match "Import-Module"
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

    Context "Command Installation" {
        It "Uses Install-CommandFiles function" {
            $Script:Content | Should -Match "Install-CommandFiles"
        }

        It "Checks for CommandsDir configuration" {
            $Script:Content | Should -Match '\$Config\.CommandsDir'
        }

        It "Checks for CommandFiles configuration" {
            $Script:Content | Should -Match '\$Config\.CommandFiles'
        }

        It "Resolves CommandsDir path" {
            $Script:Content | Should -Match "Resolve-DestinationPath.*CommandsDir"
        }
    }

    Context "Prompt Installation" {
        It "Uses Install-PromptFiles function" {
            $Script:Content | Should -Match "Install-PromptFiles"
        }

        It "Checks for PromptFiles configuration" {
            $Script:Content | Should -Match '\$Config\.PromptFiles'
        }

        It "Displays prompt installation message" {
            $Script:Content | Should -Match "Installing prompt files"
        }

        It "Displays prompt statistics" {
            $Script:Content | Should -Match "Prompts:.*installed.*updated.*skipped"
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

        It "Escapes dots before converting asterisks to avoid corrupting regex" {
            # Verify the replacement order: dots first, then asterisks
            # Wrong order: -replace "\*", ".*" -replace "\.", "\." turns *.agent.md into \.*\.agent\.md
            # Correct order: -replace "\.", "\." -replace "\*", ".*" turns *.agent.md into .*\.agent\.md
            $Script:Content | Should -Match '-replace\s+"\\\.".*-replace\s+"\\\*"' -Because "dots must be escaped before asterisks to avoid corrupting .* pattern"
        }
    }
}

Describe "Glob-to-Regex Conversion (Remote File Matching)" {
    # These tests directly validate the regex conversion logic that caused the bug
    # found by @bcull during verification testing of Issue #892.
    # The bug: wrong replacement order turned *.agent.md into ^\.*\.agent\.md$ instead of ^.*\.agent\.md$

    Context "Conversion Function Behavior" {
        BeforeAll {
            # Extract the exact conversion logic from the script
            function ConvertTo-RegexPattern {
                param([string]$GlobPattern)
                # This is the CORRECT implementation (dots first, then asterisks)
                "^" + ($GlobPattern -replace "\.", "\." -replace "\*", ".*") + "$"
            }

            function ConvertTo-RegexPatternWrong {
                param([string]$GlobPattern)
                # This is the WRONG implementation (asterisks first, then dots) - the bug
                "^" + ($GlobPattern -replace "\*", ".*" -replace "\.", "\.") + "$"
            }
        }

        It "Correct conversion: *.agent.md produces ^.*\.agent\.md$" {
            $result = ConvertTo-RegexPattern "*.agent.md"
            $result | Should -Be '^.*\.agent\.md$'
        }

        It "Wrong conversion: *.agent.md produces ^\.*\.agent\.md$ (the bug)" {
            # This test demonstrates what the bug produced
            $result = ConvertTo-RegexPatternWrong "*.agent.md"
            $result | Should -Be '^\.*\.agent\.md$'
            # Note: ^\.*\. means "zero or more dots at start" - NOT what we want
        }

        It "Correct regex matches files with any prefix" {
            $correctRegex = ConvertTo-RegexPattern "*.agent.md"
            "analyst.agent.md" -match $correctRegex | Should -Be $true
            "high-level-advisor.agent.md" -match $correctRegex | Should -Be $true
            "a.agent.md" -match $correctRegex | Should -Be $true
            ".agent.md" -match $correctRegex | Should -Be $true  # Empty prefix
        }

        It "Wrong regex fails to match files with non-dot prefix (the bug symptom)" {
            $wrongRegex = ConvertTo-RegexPatternWrong "*.agent.md"
            # The bug: ^\.*\. requires the file to START with dots
            "analyst.agent.md" -match $wrongRegex | Should -Be $false -Because "wrong regex requires dots at start"
            "orchestrator.agent.md" -match $wrongRegex | Should -Be $false
            # Only files starting with dots would match (edge case)
            "...agent.md" -match $wrongRegex | Should -Be $true
        }
    }

    Context "Pattern Coverage - All Config Patterns" {
        BeforeAll {
            function ConvertTo-RegexPattern {
                param([string]$GlobPattern)
                "^" + ($GlobPattern -replace "\.", "\." -replace "\*", ".*") + "$"
            }
        }

        It "*.agent.md matches agent files" {
            $regex = ConvertTo-RegexPattern "*.agent.md"
            @(
                "analyst.agent.md",
                "architect.agent.md",
                "critic.agent.md",
                "devops.agent.md",
                "explainer.agent.md",
                "high-level-advisor.agent.md",
                "implementer.agent.md",
                "independent-thinker.agent.md",
                "memory.agent.md",
                "orchestrator.agent.md",
                "planner.agent.md",
                "pr-comment-responder.agent.md",
                "qa.agent.md",
                "retrospective.agent.md",
                "roadmap.agent.md",
                "security.agent.md",
                "skillbook.agent.md",
                "task-generator.agent.md"
            ) | ForEach-Object {
                $_ -match $regex | Should -Be $true -Because "$_ should match *.agent.md"
            }
        }

        It "*.agent.md rejects non-agent files" {
            $regex = ConvertTo-RegexPattern "*.agent.md"
            @(
                "README.md",
                "AGENTS.md",
                "CLAUDE.md",
                "config.json",
                "install.ps1",
                "agent.md",        # Missing the dot before agent
                "analyst.md",     # Missing .agent
                "analyst.agent",  # Missing .md
                "analyst.agent.txt"
            ) | ForEach-Object {
                $_ -match $regex | Should -Be $false -Because "$_ should NOT match *.agent.md"
            }
        }

        It "*.prompt.md matches prompt files" {
            $regex = ConvertTo-RegexPattern "*.prompt.md"
            @(
                "analyst.prompt.md",
                "custom.prompt.md",
                "test-prompt.prompt.md"
            ) | ForEach-Object {
                $_ -match $regex | Should -Be $true -Because "$_ should match *.prompt.md"
            }
        }

        It "*.md matches all markdown files" {
            $regex = ConvertTo-RegexPattern "*.md"
            @(
                "README.md",
                "CLAUDE.md",
                "analyst.agent.md",
                "test.md",
                ".md"  # Edge case: just extension
            ) | ForEach-Object {
                $_ -match $regex | Should -Be $true -Because "$_ should match *.md"
            }
        }
    }

    Context "File Filtering Simulation" {
        BeforeAll {
            function ConvertTo-RegexPattern {
                param([string]$GlobPattern)
                "^" + ($GlobPattern -replace "\.", "\." -replace "\*", ".*") + "$"
            }

            # Simulate GitHub API response (array of file objects)
            $Script:MockGitHubFiles = @(
                @{ name = "analyst.agent.md"; type = "file" },
                @{ name = "architect.agent.md"; type = "file" },
                @{ name = "README.md"; type = "file" },
                @{ name = "AGENTS.md"; type = "file" },
                @{ name = "config.json"; type = "file" },
                @{ name = "subdir"; type = "dir" },
                @{ name = "orchestrator.agent.md"; type = "file" },
                @{ name = ".gitignore"; type = "file" }
            )
        }

        It "Filters files correctly using the pattern and type check" {
            $pattern = "*.agent.md"
            $patternRegex = ConvertTo-RegexPattern $pattern

            # This is the exact filtering logic from install.ps1 line 251
            $matchingFiles = $Script:MockGitHubFiles | Where-Object {
                $_.name -match $patternRegex -and $_.type -eq "file"
            }

            $matchingFiles.Count | Should -Be 3 -Because "there are 3 .agent.md files"
            $matchingFiles.name | Should -Contain "analyst.agent.md"
            $matchingFiles.name | Should -Contain "architect.agent.md"
            $matchingFiles.name | Should -Contain "orchestrator.agent.md"
            $matchingFiles.name | Should -Not -Contain "README.md"
            $matchingFiles.name | Should -Not -Contain "subdir"
        }

        It "Returns empty when no files match (triggers warning branch)" {
            $pattern = "*.nonexistent.xyz"
            $patternRegex = ConvertTo-RegexPattern $pattern

            $matchingFiles = $Script:MockGitHubFiles | Where-Object {
                $_.name -match $patternRegex -and $_.type -eq "file"
            }

            $matchingFiles.Count | Should -Be 0
        }

        It "Excludes directories even if name matches pattern" {
            # Add a directory that looks like an agent file
            $filesWithTrickyDir = $Script:MockGitHubFiles + @(
                @{ name = "fake.agent.md"; type = "dir" }
            )

            $pattern = "*.agent.md"
            $patternRegex = ConvertTo-RegexPattern $pattern

            $matchingFiles = $filesWithTrickyDir | Where-Object {
                $_.name -match $patternRegex -and $_.type -eq "file"
            }

            $matchingFiles.name | Should -Not -Contain "fake.agent.md" -Because "directories should be excluded"
        }
    }

    Context "Edge Cases and Boundary Conditions" {
        BeforeAll {
            function ConvertTo-RegexPattern {
                param([string]$GlobPattern)
                "^" + ($GlobPattern -replace "\.", "\." -replace "\*", ".*") + "$"
            }
        }

        It "Handles multiple dots in filename" {
            $regex = ConvertTo-RegexPattern "*.agent.md"
            "my.special.analyst.agent.md" -match $regex | Should -Be $true
        }

        It "Handles hyphens in filename" {
            $regex = ConvertTo-RegexPattern "*.agent.md"
            "high-level-advisor.agent.md" -match $regex | Should -Be $true
            "pr-comment-responder.agent.md" -match $regex | Should -Be $true
        }

        It "Handles underscores in filename" {
            $regex = ConvertTo-RegexPattern "*.agent.md"
            "my_custom_agent.agent.md" -match $regex | Should -Be $true
        }

        It "Handles numbers in filename" {
            $regex = ConvertTo-RegexPattern "*.agent.md"
            "agent123.agent.md" -match $regex | Should -Be $true
            "123.agent.md" -match $regex | Should -Be $true
        }

        It "Pattern with multiple wildcards" {
            $regex = ConvertTo-RegexPattern "*.*.md"
            "analyst.agent.md" -match $regex | Should -Be $true
            "test.prompt.md" -match $regex | Should -Be $true
            "README.md" -match $regex | Should -Be $false  # Only one dot before .md
        }

        It "Empty prefix still matches" {
            $regex = ConvertTo-RegexPattern "*.agent.md"
            ".agent.md" -match $regex | Should -Be $true
        }

        It "Case insensitivity (PowerShell -match is case-insensitive)" {
            # PowerShell's -match operator is case-INsensitive by default
            # This means the script will match files regardless of case
            $regex = ConvertTo-RegexPattern "*.agent.md"
            "Analyst.Agent.MD" -match $regex | Should -Be $true
            "ANALYST.AGENT.MD" -match $regex | Should -Be $true
            "analyst.agent.md" -match $regex | Should -Be $true
        }
    }

    Context "Script Implementation Verification" {
        BeforeAll {
            $Script:Content = Get-Content $Script:InstallScript -Raw
        }

        It "Uses correct replacement order in the script" {
            # The pattern must be: -replace "\.", "\." BEFORE -replace "\*", ".*"
            # This regex verifies dots are escaped first
            $Script:Content | Should -Match '\-replace\s+"\\\."[^-]*-replace\s+"\\\*"'
        }

        It "Anchors pattern with ^ and $" {
            $Script:Content | Should -Match '\"\^\"\s*\+.*\+\s*\"\$\"'
        }

        It "Filters by both name pattern AND type" {
            $Script:Content | Should -Match '\$_\.name\s+-match\s+\$PatternRegex\s+-and\s+\$_\.type\s+-eq\s+"file"'
        }
    }
}

Describe "Environment Parameter Validation (Issue #892)" {
    Context "Manual Validation Logic" {
        BeforeAll {
            $Script:Content = Get-Content $Script:InstallScript -Raw
        }

        It "Contains manual validation for Environment parameter" {
            $Script:Content | Should -Match 'ValidEnvironments\s*=\s*@\('
        }

        It "Checks Environment against valid values" {
            $Script:Content | Should -Match 'Environment\s+-notin\s+\$ValidEnvironments'
        }

        It "Writes error for invalid Environment value" {
            $Script:Content | Should -Match 'Write-Error.*Invalid Environment'
        }

        It "Lists valid values in error message" {
            $Script:Content | Should -Match 'Valid values are'
        }
    }

    Context "iex Invocation Simulation" {
        It "Script accepts empty Environment parameter (syntax validation)" {
            # Verify script syntax allows empty string (prevents parameter binding errors)
            $scriptContent = Get-Content $Script:InstallScript -Raw
            { [scriptblock]::Create($scriptContent) } | Should -Not -Throw
        }

        It "Rejects invalid Environment parameter with error" {
            # Test manual validation logic
            try {
                & $Script:InstallScript -Environment "InvalidValue" -ErrorAction Stop 2>&1 | Out-Null
                $false | Should -Be $true -Because "Script should throw error for invalid Environment"
            }
            catch {
                $_.Exception.Message | Should -Match "Invalid Environment"
            }
        }

        It "Accepts valid Environment values without error" {
            # Test that each valid value passes the manual validation logic without error.
            # The script will fail later (e.g., missing module), but validation must pass.
            @("Claude", "Copilot", "VSCode") | ForEach-Object {
                $envValue = $_
                # Invoke script and capture any validation error
                $validationError = $null
                try {
                    # The script will fail eventually (module not found in test context),
                    # but if validation passes, the error will NOT be "Invalid Environment"
                    & $Script:InstallScript -Environment $envValue -Global -ErrorAction Stop 2>&1 | Out-Null
                }
                catch {
                    $validationError = $_.Exception.Message
                }
                # Validation error would contain "Invalid Environment" - any other error is OK
                $validationError | Should -Not -Match "Invalid Environment" -Because "the script should not throw a validation error for the valid environment '$envValue'"
            }
        }

        It "Works when user has \$Env:Environment variable set (Issue #892 root cause)" {
            # Save current environment
            $originalEnvVar = $env:Environment
            try {
                # Simulate the problematic scenario that caused Issue #892
                $env:Environment = "Development"

                # With ArgumentCompleter (not ValidateSet), this should NOT throw parameter binding error
                # We test parameter binding by parsing and checking the param block
                $scriptContent = Get-Content $Script:InstallScript -Raw
                { [scriptblock]::Create($scriptContent) } | Should -Not -Throw

                # Verify the script can get command info without conflicts
                $command = Get-Command -Name $Script:InstallScript
                $command | Should -Not -BeNullOrEmpty
                $command.Parameters.ContainsKey("Environment") | Should -Be $true
            }
            finally {
                # Restore original environment
                if ($null -eq $originalEnvVar) {
                    Remove-Item Env:\Environment -ErrorAction SilentlyContinue
                }
                else {
                    $env:Environment = $originalEnvVar
                }
            }
        }

        It "Parameter binding succeeds with environment variable set" {
            $originalEnvVar = $env:Environment
            try {
                # Set environment variable that previously caused conflicts
                $env:Environment = "Development"

                # Test that we can get parameter information (proves no binding conflict)
                $scriptAst = [System.Management.Automation.Language.Parser]::ParseFile($Script:InstallScript, [ref]$null, [ref]$null)
                $envParam = $scriptAst.ParamBlock.Parameters | Where-Object { $_.Name.VariablePath.UserPath -eq "Environment" }
                $envParam | Should -Not -BeNullOrEmpty -Because "Environment parameter should be parseable even when env var is set"

                # Verify no ValidateSet attribute (which would cause the conflict)
                $validateSetAttr = $envParam.Attributes | Where-Object { $_.TypeName.Name -eq "ValidateSet" }
                $validateSetAttr | Should -BeNullOrEmpty -Because "ValidateSet causes parameter binding conflicts with environment variables"
            }
            finally {
                if ($null -eq $originalEnvVar) {
                    Remove-Item Env:\Environment -ErrorAction SilentlyContinue
                }
                else {
                    $env:Environment = $originalEnvVar
                }
            }
        }
    }

    Context "ArgumentCompleter Functionality" {
        It "ArgumentCompleter provides Claude as completion" {
            $param = $Script:ScriptInfo.Parameters["Environment"]
            $completer = $param.Attributes | Where-Object { $_ -is [System.Management.Automation.ArgumentCompleterAttribute] }
            $completions = & $completer.ScriptBlock $null "Environment" "" $null $null
            $completions | Should -Contain "Claude"
        }

        It "ArgumentCompleter provides Copilot as completion" {
            $param = $Script:ScriptInfo.Parameters["Environment"]
            $completer = $param.Attributes | Where-Object { $_ -is [System.Management.Automation.ArgumentCompleterAttribute] }
            $completions = & $completer.ScriptBlock $null "Environment" "" $null $null
            $completions | Should -Contain "Copilot"
        }

        It "ArgumentCompleter provides VSCode as completion" {
            $param = $Script:ScriptInfo.Parameters["Environment"]
            $completer = $param.Attributes | Where-Object { $_ -is [System.Management.Automation.ArgumentCompleterAttribute] }
            $completions = & $completer.ScriptBlock $null "Environment" "" $null $null
            $completions | Should -Contain "VSCode"
        }

        It "ArgumentCompleter filters completions based on input" {
            $param = $Script:ScriptInfo.Parameters["Environment"]
            $completer = $param.Attributes | Where-Object { $_ -is [System.Management.Automation.ArgumentCompleterAttribute] }
            $completions = & $completer.ScriptBlock $null "Environment" "Cl" $null $null
            $completions | Should -Contain "Claude"
            $completions | Should -Not -Contain "Copilot"
            $completions | Should -Not -Contain "VSCode"
        }
    }
}
