BeforeAll {
    $script:scriptPath = "$PSScriptRoot/../scripts/Validate-ActionSHAPinning.ps1"
}

Describe "Validate-ActionSHAPinning" {
    Context "Script Validation" {
        It "Script file exists" {
            Test-Path $script:scriptPath | Should -Be $true
        }

        It "Script can be parsed without errors" {
            { $null = [System.Management.Automation.PSParser]::Tokenize((Get-Content $script:scriptPath -Raw), [ref]$null) } | Should -Not -Throw
        }
    }

    Context "Parameter Validation" {
        It "Accepts valid Format parameter values" {
            { & $script:scriptPath -Path "." -Format "console" } | Should -Not -Throw
            { & $script:scriptPath -Path "." -Format "markdown" } | Should -Not -Throw
            { & $script:scriptPath -Path "." -Format "json" } | Should -Not -Throw
        }

        It "Has CI switch parameter" {
            $params = (Get-Command $script:scriptPath).Parameters
            $params.ContainsKey('CI') | Should -Be $true
            $params['CI'].ParameterType.Name | Should -Be 'SwitchParameter'
        }
    }

    Context "Workflow Detection" {
        It "Detects version tag violation" {
            $testDir = Join-Path $TestDrive "version-tag-test"
            $workflowDir = Join-Path $testDir ".github/workflows"
            New-Item -ItemType Directory -Path $workflowDir -Force | Out-Null

            $workflowContent = @"
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"@
            $workflowFile = Join-Path $workflowDir "test.yml"
            Set-Content -Path $workflowFile -Value $workflowContent

            $result = & $script:scriptPath -Path $testDir -Format "json" | ConvertFrom-Json
            $result.status | Should -Be "fail"
            $result.violations.Count | Should -BeGreaterThan 0
        }

        It "Passes with SHA-pinned action" {
            $testDir = Join-Path $TestDrive "sha-pinned-test"
            $workflowDir = Join-Path $testDir ".github/workflows"
            New-Item -ItemType Directory -Path $workflowDir -Force | Out-Null

            $workflowContent = @"
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4
"@
            $workflowFile = Join-Path $workflowDir "test-sha.yml"
            Set-Content -Path $workflowFile -Value $workflowContent

            $result = & $script:scriptPath -Path $testDir -Format "json" | ConvertFrom-Json
            $result.status | Should -Be "pass"
        }

        It "Ignores local actions" {
            $testDir = Join-Path $TestDrive "local-action-test"
            $workflowDir = Join-Path $testDir ".github/workflows"
            New-Item -ItemType Directory -Path $workflowDir -Force | Out-Null

            $workflowContent = @"
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: ./.github/actions/my-action
"@
            $workflowFile = Join-Path $workflowDir "test-local.yml"
            Set-Content -Path $workflowFile -Value $workflowContent

            $result = & $script:scriptPath -Path $testDir -Format "json" | ConvertFrom-Json
            $result.status | Should -Be "pass"
        }
    }

    Context "Output Formats" {
        BeforeAll {
            $script:testDir = Join-Path $TestDrive "format-test"
            New-Item -ItemType Directory -Path $script:testDir -Force | Out-Null
            $script:workflowDir = Join-Path $script:testDir ".github/workflows"
            New-Item -ItemType Directory -Path $script:workflowDir -Force | Out-Null
            
            $workflowContent = @"
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4
"@
            $workflowFile = Join-Path $script:workflowDir "passing.yml"
            Set-Content -Path $workflowFile -Value $workflowContent
        }

        It "JSON format produces valid JSON" {
            $output = & $script:scriptPath -Path $script:testDir -Format "json"
            { $output | ConvertFrom-Json } | Should -Not -Throw
        }

        It "Markdown format includes expected sections" {
            $output = (& $script:scriptPath -Path $script:testDir -Format "markdown") -join "`n"
            $output | Should -Match "GitHub Actions SHA Pinning Validation"
            $output | Should -Match "Status"
        }
    }

    Context "Exit Codes" {
        BeforeAll {
            $script:testDir = Join-Path $TestDrive "exitcode-test"
            New-Item -ItemType Directory -Path $script:testDir -Force | Out-Null
            $script:workflowDir = Join-Path $script:testDir ".github/workflows"
            New-Item -ItemType Directory -Path $script:workflowDir -Force | Out-Null
        }

        It "Returns exit code 0 when all actions are SHA-pinned" {
            $workflowContent = @"
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4
"@
            $workflowFile = Join-Path $script:workflowDir "pass.yml"
            Set-Content -Path $workflowFile -Value $workflowContent

            & $script:scriptPath -Path $script:testDir
            $LASTEXITCODE | Should -Be 0
        }

        It "Returns exit code 1 in CI mode when violations found" {
            $workflowContent = @"
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"@
            $workflowFile = Join-Path $script:workflowDir "fail.yml"
            Set-Content -Path $workflowFile -Value $workflowContent

            & $script:scriptPath -Path $script:testDir -CI
            $LASTEXITCODE | Should -Be 1
        }
    }
}
