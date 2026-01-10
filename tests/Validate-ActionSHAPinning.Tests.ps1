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

        It "Detects version tag with alpha suffix" {
            $testDir = Join-Path $TestDrive "version-alpha-test"
            $workflowDir = Join-Path $testDir ".github/workflows"
            New-Item -ItemType Directory -Path $workflowDir -Force | Out-Null

            $workflowContent = @"
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4-alpha
"@
            $workflowFile = Join-Path $workflowDir "test.yml"
            Set-Content -Path $workflowFile -Value $workflowContent

            $result = & $script:scriptPath -Path $testDir -Format "json" | ConvertFrom-Json
            $result.status | Should -Be "fail"
            $result.violations.Count | Should -BeGreaterThan 0
        }

        It "Detects version tag with beta suffix" {
            $testDir = Join-Path $TestDrive "version-beta-test"
            $workflowDir = Join-Path $testDir ".github/workflows"
            New-Item -ItemType Directory -Path $workflowDir -Force | Out-Null

            $workflowContent = @"
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-node@v3.2.1-beta
"@
            $workflowFile = Join-Path $workflowDir "test.yml"
            Set-Content -Path $workflowFile -Value $workflowContent

            $result = & $script:scriptPath -Path $testDir -Format "json" | ConvertFrom-Json
            $result.status | Should -Be "fail"
            $result.violations.Count | Should -BeGreaterThan 0
        }

        It "Detects version tag with rc suffix" {
            $testDir = Join-Path $TestDrive "version-rc-test"
            $workflowDir = Join-Path $testDir ".github/workflows"
            New-Item -ItemType Directory -Path $workflowDir -Force | Out-Null

            $workflowContent = @"
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/cache@v2.0.0-rc1
"@
            $workflowFile = Join-Path $workflowDir "test.yml"
            Set-Content -Path $workflowFile -Value $workflowContent

            $result = & $script:scriptPath -Path $testDir -Format "json" | ConvertFrom-Json
            $result.status | Should -Be "fail"
            $result.violations.Count | Should -BeGreaterThan 0
        }

        It "Does not match SHA that starts with v-like hex pattern" {
            $testDir = Join-Path $TestDrive "sha-vlike-test"
            $workflowDir = Join-Path $testDir ".github/workflows"
            New-Item -ItemType Directory -Path $workflowDir -Force | Out-Null

            $workflowContent = @"
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5
"@
            $workflowFile = Join-Path $workflowDir "test.yml"
            Set-Content -Path $workflowFile -Value $workflowContent

            $result = & $script:scriptPath -Path $testDir -Format "json" | ConvertFrom-Json
            $result.status | Should -Be "pass"
        }
    }

    Context "SEMVER Variations" {
        It "Detects major version only (v1)" {
            $testDir = Join-Path $TestDrive "semver-major-test"
            $workflowDir = Join-Path $testDir ".github/workflows"
            New-Item -ItemType Directory -Path $workflowDir -Force | Out-Null

            $workflowContent = @"
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v1
"@
            $workflowFile = Join-Path $workflowDir "test.yml"
            Set-Content -Path $workflowFile -Value $workflowContent

            $result = & $script:scriptPath -Path $testDir -Format "json" | ConvertFrom-Json
            $result.status | Should -Be "fail"
            $result.violations.Count | Should -BeGreaterThan 0
        }

        It "Detects major.minor version (v2.1)" {
            $testDir = Join-Path $TestDrive "semver-minor-test"
            $workflowDir = Join-Path $testDir ".github/workflows"
            New-Item -ItemType Directory -Path $workflowDir -Force | Out-Null

            $workflowContent = @"
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-python@v2.1
"@
            $workflowFile = Join-Path $workflowDir "test.yml"
            Set-Content -Path $workflowFile -Value $workflowContent

            $result = & $script:scriptPath -Path $testDir -Format "json" | ConvertFrom-Json
            $result.status | Should -Be "fail"
            $result.violations.Count | Should -BeGreaterThan 0
        }

        It "Detects major.minor.patch version (v3.2.1)" {
            $testDir = Join-Path $TestDrive "semver-patch-test"
            $workflowDir = Join-Path $testDir ".github/workflows"
            New-Item -ItemType Directory -Path $workflowDir -Force | Out-Null

            $workflowContent = @"
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/cache@v3.2.1
"@
            $workflowFile = Join-Path $workflowDir "test.yml"
            Set-Content -Path $workflowFile -Value $workflowContent

            $result = & $script:scriptPath -Path $testDir -Format "json" | ConvertFrom-Json
            $result.status | Should -Be "fail"
            $result.violations.Count | Should -BeGreaterThan 0
        }

        It "Detects prerelease with alpha suffix (v1.0.0-alpha)" {
            $testDir = Join-Path $TestDrive "semver-alpha-test"
            $workflowDir = Join-Path $testDir ".github/workflows"
            New-Item -ItemType Directory -Path $workflowDir -Force | Out-Null

            $workflowContent = @"
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v1.0.0-alpha
"@
            $workflowFile = Join-Path $workflowDir "test.yml"
            Set-Content -Path $workflowFile -Value $workflowContent

            $result = & $script:scriptPath -Path $testDir -Format "json" | ConvertFrom-Json
            $result.status | Should -Be "fail"
            $result.violations.Count | Should -BeGreaterThan 0
        }

        It "Detects prerelease with numeric suffix (v1.0.0-alpha.1)" {
            $testDir = Join-Path $TestDrive "semver-alpha-numeric-test"
            $workflowDir = Join-Path $testDir ".github/workflows"
            New-Item -ItemType Directory -Path $workflowDir -Force | Out-Null

            $workflowContent = @"
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-node@v1.0.0-alpha.1
"@
            $workflowFile = Join-Path $workflowDir "test.yml"
            Set-Content -Path $workflowFile -Value $workflowContent

            $result = & $script:scriptPath -Path $testDir -Format "json" | ConvertFrom-Json
            $result.status | Should -Be "fail"
            $result.violations.Count | Should -BeGreaterThan 0
        }

        It "Detects prerelease with dotted identifiers (v1.0.0-0.3.7)" {
            $testDir = Join-Path $TestDrive "semver-dotted-test"
            $workflowDir = Join-Path $testDir ".github/workflows"
            New-Item -ItemType Directory -Path $workflowDir -Force | Out-Null

            $workflowContent = @"
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/cache@v1.0.0-0.3.7
"@
            $workflowFile = Join-Path $workflowDir "test.yml"
            Set-Content -Path $workflowFile -Value $workflowContent

            $result = & $script:scriptPath -Path $testDir -Format "json" | ConvertFrom-Json
            $result.status | Should -Be "fail"
            $result.violations.Count | Should -BeGreaterThan 0
        }

        It "Detects prerelease with complex identifiers (v1.0.0-x.7.z.92)" {
            $testDir = Join-Path $TestDrive "semver-complex-test"
            $workflowDir = Join-Path $testDir ".github/workflows"
            New-Item -ItemType Directory -Path $workflowDir -Force | Out-Null

            $workflowContent = @"
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/upload-artifact@v1.0.0-x.7.z.92
"@
            $workflowFile = Join-Path $workflowDir "test.yml"
            Set-Content -Path $workflowFile -Value $workflowContent

            $result = & $script:scriptPath -Path $testDir -Format "json" | ConvertFrom-Json
            $result.status | Should -Be "fail"
            $result.violations.Count | Should -BeGreaterThan 0
        }

        It "Detects version with build metadata (v1.0.0+20130313144700)" {
            $testDir = Join-Path $TestDrive "semver-build-test"
            $workflowDir = Join-Path $testDir ".github/workflows"
            New-Item -ItemType Directory -Path $workflowDir -Force | Out-Null

            $workflowContent = @"
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v1.0.0+20130313144700
"@
            $workflowFile = Join-Path $workflowDir "test.yml"
            Set-Content -Path $workflowFile -Value $workflowContent

            $result = & $script:scriptPath -Path $testDir -Format "json" | ConvertFrom-Json
            $result.status | Should -Be "fail"
            $result.violations.Count | Should -BeGreaterThan 0
        }

        It "Detects version with prerelease and build metadata (v1.0.0-beta+exp.sha.5114f85)" {
            $testDir = Join-Path $TestDrive "semver-full-test"
            $workflowDir = Join-Path $testDir ".github/workflows"
            New-Item -ItemType Directory -Path $workflowDir -Force | Out-Null

            $workflowContent = @"
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-python@v1.0.0-beta+exp.sha.5114f85
"@
            $workflowFile = Join-Path $workflowDir "test.yml"
            Set-Content -Path $workflowFile -Value $workflowContent

            $result = & $script:scriptPath -Path $testDir -Format "json" | ConvertFrom-Json
            $result.status | Should -Be "fail"
            $result.violations.Count | Should -BeGreaterThan 0
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
