Describe "Validate-ActionSHAPinning" {
    BeforeAll {
        $scriptPath = "$PSScriptRoot/../Validate-ActionSHAPinning.ps1"
    }

    Context "Script Validation" {
        It "Should exist" {
            $scriptPath | Should -Exist
        }

        It "Should have valid PowerShell syntax" {
            $errors = $null
            $null = [System.Management.Automation.PSParser]::Tokenize(
                (Get-Content -Path $scriptPath -Raw), [ref]$errors
            )
            $errors.Count | Should -Be 0
        }

        It "Should be executable" {
            Test-Path $scriptPath | Should -Be $true
            (Get-Item $scriptPath).Extension | Should -Be ".ps1"
        }
    }

    Context "Functional Tests" {
        It "Should execute without errors when no workflows found" {
            $tempDir = New-Item -ItemType Directory -Path (Join-Path $TestDrive "no-workflows") -Force
            { & $scriptPath -Path $tempDir.FullName } | Should -Not -Throw
        }

        It "Should detect SHA-pinned actions correctly" {
            # Create test workflow with SHA-pinned action
            $workflowDir = New-Item -ItemType Directory -Path (Join-Path $TestDrive "test-repo/.github/workflows") -Force
            $workflowContent = @'
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4
'@
            Set-Content -Path (Join-Path $workflowDir "test.yml") -Value $workflowContent
            
            $result = & $scriptPath -Path (Split-Path $workflowDir.Parent.Parent.FullName) -Format json | ConvertFrom-Json
            $result.summary.violations | Should -Be 0
        }
    }
}
