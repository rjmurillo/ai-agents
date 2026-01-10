#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Invoke-SessionInitializationEnforcer.ps1

.DESCRIPTION
    Tests the SessionStart hook that blocks working on main/master branches
    and injects git state into Claude's context.
#>

BeforeAll {
    $Script:HookPath = Join-Path $PSScriptRoot ".." ".claude" "hooks" "SessionStart" "Invoke-SessionInitializationEnforcer.ps1"

    if (-not (Test-Path $Script:HookPath)) {
        throw "Hook script not found at: $Script:HookPath"
    }

    # Helper to invoke hook with environment setup
    function Invoke-HookInContext {
        param(
            [string]$HookPath = $Script:HookPath,
            [string]$ProjectDir = $null,
            [string]$WorkingDir = $null
        )

        $tempOutput = [System.IO.Path]::GetTempFileName()
        $tempError = [System.IO.Path]::GetTempFileName()
        $tempScript = [System.IO.Path]::GetTempFileName() + ".ps1"

        try {
            # Create wrapper script to set env and working dir
            $wrapperContent = @"
`$env:CLAUDE_PROJECT_DIR = '$($ProjectDir -replace "'", "''")'
$(if ($WorkingDir) { "Set-Location '$($WorkingDir -replace "'", "''")'" })
& '$($HookPath -replace "'", "''")'
exit `$LASTEXITCODE
"@
            Set-Content -Path $tempScript -Value $wrapperContent

            $process = Start-Process -FilePath "pwsh" -ArgumentList "-NoProfile", "-File", $tempScript -RedirectStandardOutput $tempOutput -RedirectStandardError $tempError -PassThru -Wait -NoNewWindow
            $output = Get-Content $tempOutput -Raw -ErrorAction SilentlyContinue
            $errorOutput = Get-Content $tempError -Raw -ErrorAction SilentlyContinue

            return @{
                Output = @($output, $errorOutput) | Where-Object { $_ }
                ExitCode = $process.ExitCode
            }
        }
        finally {
            Remove-Item $tempOutput, $tempError, $tempScript -Force -ErrorAction SilentlyContinue
        }
    }
}

Describe "Invoke-SessionInitializationEnforcer" {
    Context "Protected branch blocking" {
        BeforeAll {
            # Create test git repo on main branch
            $Script:TestRootMain = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-main-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRootMain -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootMain ".claude/hooks/SessionStart") -Force | Out-Null

            # Copy hook
            $Script:TempHookPathMain = Join-Path $Script:TestRootMain ".claude/hooks/SessionStart/Invoke-SessionInitializationEnforcer.ps1"
            Copy-Item -Path $Script:HookPath -Destination $Script:TempHookPathMain -Force

            # Init git repo on main
            Push-Location $Script:TestRootMain
            git init --quiet
            git config user.email "test@test.com"
            git config user.name "Test"
            Set-Content -Path (Join-Path $Script:TestRootMain "README.md") -Value "# Test"
            git add README.md
            git commit -m "Initial" --quiet
            # Ensure on main branch
            git checkout -b main 2>$null
            git checkout main 2>$null
            Pop-Location
        }

        AfterAll {
            if (Test-Path $Script:TestRootMain) {
                Remove-Item -Path $Script:TestRootMain -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Blocks when on main branch (exit 2)" {
            $result = Invoke-HookInContext -HookPath $Script:TempHookPathMain -ProjectDir $Script:TestRootMain -WorkingDir $Script:TestRootMain
            $result.ExitCode | Should -Be 2
        }

        It "Outputs blocking message about protected branch" {
            $result = Invoke-HookInContext -HookPath $Script:TempHookPathMain -ProjectDir $Script:TestRootMain -WorkingDir $Script:TestRootMain
            $output = $result.Output -join "`n"
            $output | Should -Match "BLOCKED"
            $output | Should -Match "main"
        }

        It "Suggests creating feature branch" {
            $result = Invoke-HookInContext -HookPath $Script:TempHookPathMain -ProjectDir $Script:TestRootMain -WorkingDir $Script:TestRootMain
            $output = $result.Output -join "`n"
            $output | Should -Match "git checkout"
            $output | Should -Match "feat/"
        }
    }

    Context "Master branch also blocked" {
        BeforeAll {
            # Create test git repo on master branch
            $Script:TestRootMaster = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-master-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRootMaster -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootMaster ".claude/hooks/SessionStart") -Force | Out-Null

            # Copy hook
            $Script:TempHookPathMaster = Join-Path $Script:TestRootMaster ".claude/hooks/SessionStart/Invoke-SessionInitializationEnforcer.ps1"
            Copy-Item -Path $Script:HookPath -Destination $Script:TempHookPathMaster -Force

            # Init git repo on master
            Push-Location $Script:TestRootMaster
            git init --quiet --initial-branch=master
            git config user.email "test@test.com"
            git config user.name "Test"
            Set-Content -Path (Join-Path $Script:TestRootMaster "README.md") -Value "# Test"
            git add README.md
            git commit -m "Initial" --quiet
            Pop-Location
        }

        AfterAll {
            if (Test-Path $Script:TestRootMaster) {
                Remove-Item -Path $Script:TestRootMaster -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Blocks when on master branch (exit 2)" {
            $result = Invoke-HookInContext -HookPath $Script:TempHookPathMaster -ProjectDir $Script:TestRootMaster -WorkingDir $Script:TestRootMaster
            $result.ExitCode | Should -Be 2
        }
    }

    Context "Feature branch allows" {
        BeforeAll {
            # Create test git repo on feature branch
            $Script:TestRootFeature = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-feature-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRootFeature -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootFeature ".claude/hooks/SessionStart") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootFeature ".agents/sessions") -Force | Out-Null

            # Copy hook
            $Script:TempHookPathFeature = Join-Path $Script:TestRootFeature ".claude/hooks/SessionStart/Invoke-SessionInitializationEnforcer.ps1"
            Copy-Item -Path $Script:HookPath -Destination $Script:TempHookPathFeature -Force

            # Init git repo on feature branch
            Push-Location $Script:TestRootFeature
            git init --quiet
            git config user.email "test@test.com"
            git config user.name "Test"
            Set-Content -Path (Join-Path $Script:TestRootFeature "README.md") -Value "# Test"
            git add README.md
            git commit -m "Initial" --quiet
            git checkout -b feat/test-feature --quiet
            Pop-Location
        }

        AfterAll {
            if (Test-Path $Script:TestRootFeature) {
                Remove-Item -Path $Script:TestRootFeature -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Allows when on feature branch (exit 0)" {
            $result = Invoke-HookInContext -HookPath $Script:TempHookPathFeature -ProjectDir $Script:TestRootFeature -WorkingDir $Script:TestRootFeature
            $result.ExitCode | Should -Be 0
        }

        It "Outputs branch confirmation" {
            $result = Invoke-HookInContext -HookPath $Script:TempHookPathFeature -ProjectDir $Script:TestRootFeature -WorkingDir $Script:TestRootFeature
            $output = $result.Output -join "`n"
            $output | Should -Match "feat/test-feature"
            $output | Should -Match "Passed"
        }

        It "Includes git status in output" {
            $result = Invoke-HookInContext -HookPath $Script:TempHookPathFeature -ProjectDir $Script:TestRootFeature -WorkingDir $Script:TestRootFeature
            $output = $result.Output -join "`n"
            $output | Should -Match "Git Status"
        }

        It "Includes recent commits in output" {
            $result = Invoke-HookInContext -HookPath $Script:TempHookPathFeature -ProjectDir $Script:TestRootFeature -WorkingDir $Script:TestRootFeature
            $output = $result.Output -join "`n"
            $output | Should -Match "Recent Commits"
            $output | Should -Match "Initial"
        }
    }

    Context "Session log detection" {
        BeforeAll {
            # Create test git repo with session log
            $Script:TestRootWithLog = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-withlog-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRootWithLog -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootWithLog ".claude/hooks/SessionStart") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootWithLog ".agents/sessions") -Force | Out-Null

            # Copy hook
            $Script:TempHookPathWithLog = Join-Path $Script:TestRootWithLog ".claude/hooks/SessionStart/Invoke-SessionInitializationEnforcer.ps1"
            Copy-Item -Path $Script:HookPath -Destination $Script:TempHookPathWithLog -Force

            # Create session log
            $today = Get-Date -Format "yyyy-MM-dd"
            Set-Content -Path (Join-Path $Script:TestRootWithLog ".agents/sessions/$today-session-999.json") -Value "{}"

            # Init git repo
            Push-Location $Script:TestRootWithLog
            git init --quiet
            git config user.email "test@test.com"
            git config user.name "Test"
            Set-Content -Path (Join-Path $Script:TestRootWithLog "README.md") -Value "# Test"
            git add README.md
            git commit -m "Initial" --quiet
            git checkout -b feat/test --quiet
            Pop-Location
        }

        AfterAll {
            if (Test-Path $Script:TestRootWithLog) {
                Remove-Item -Path $Script:TestRootWithLog -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Reports session log exists" {
            $result = Invoke-HookInContext -HookPath $Script:TempHookPathWithLog -ProjectDir $Script:TestRootWithLog -WorkingDir $Script:TestRootWithLog
            $output = $result.Output -join "`n"
            $output | Should -Match "Session log exists"
        }
    }

    Context "Non-git directory handling" {
        BeforeAll {
            # Create test environment without git
            $Script:TestRootNoGit = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-nogit-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRootNoGit -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootNoGit ".claude/hooks/SessionStart") -Force | Out-Null

            # Copy hook
            $Script:TempHookPathNoGit = Join-Path $Script:TestRootNoGit ".claude/hooks/SessionStart/Invoke-SessionInitializationEnforcer.ps1"
            Copy-Item -Path $Script:HookPath -Destination $Script:TempHookPathNoGit -Force
        }

        AfterAll {
            if (Test-Path $Script:TestRootNoGit) {
                Remove-Item -Path $Script:TestRootNoGit -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Handles non-git directory gracefully (exit 0 - fail open)" {
            $result = Invoke-HookInContext -HookPath $Script:TempHookPathNoGit -ProjectDir $Script:TestRootNoGit -WorkingDir $Script:TestRootNoGit
            $result.ExitCode | Should -Be 0
        }
    }

    Context "Script structure" {
        It "Script parses without errors" {
            $errors = $null
            $null = [System.Management.Automation.Language.Parser]::ParseFile($Script:HookPath, [ref]$null, [ref]$errors)
            $errors | Should -BeNullOrEmpty
        }
    }
}
