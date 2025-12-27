Describe "New-ValidatedPR" {
    BeforeAll {
        $script:scriptPath = Join-Path $PSScriptRoot ".." "scripts" "New-ValidatedPR.ps1"
        $script:skillPath = Join-Path $PSScriptRoot ".." ".claude" "skills" "github" "scripts" "pr" "New-PR.ps1"
    }

    Context "When creating a validated PR" {
        It "Should exist" {
            Test-Path $script:scriptPath | Should -Be $true
        }

        It "Should have valid PowerShell syntax" {
            {
                $null = [System.Management.Automation.PSParser]::Tokenize(
                    (Get-Content $script:scriptPath -Raw),
                    [ref]$null
                )
            } | Should -Not -Throw
        }

        It "Should accept -Title parameter" {
            $params = (Get-Command $script:scriptPath).Parameters
            $params.ContainsKey('Title') | Should -Be $true
        }

        It "Should accept -Body parameter" {
            $params = (Get-Command $script:scriptPath).Parameters
            $params.ContainsKey('Body') | Should -Be $true
        }

        It "Should accept -BodyFile parameter" {
            $params = (Get-Command $script:scriptPath).Parameters
            $params.ContainsKey('BodyFile') | Should -Be $true
        }

        It "Should accept -SkipValidation parameter (not Force)" {
            $params = (Get-Command $script:scriptPath).Parameters
            $params.ContainsKey('SkipValidation') | Should -Be $true
            $params.ContainsKey('Force') | Should -Be $false
        }

        It "Should accept -AuditReason parameter" {
            $params = (Get-Command $script:scriptPath).Parameters
            $params.ContainsKey('AuditReason') | Should -Be $true
        }

        It "Should accept -Web parameter" {
            $params = (Get-Command $script:scriptPath).Parameters
            $params.ContainsKey('Web') | Should -Be $true
        }

        It "Should accept -Draft parameter" {
            $params = (Get-Command $script:scriptPath).Parameters
            $params.ContainsKey('Draft') | Should -Be $true
        }

        It "Should accept -Base parameter" {
            $params = (Get-Command $script:scriptPath).Parameters
            $params.ContainsKey('Base') | Should -Be $true
        }

        It "Should accept -Head parameter" {
            $params = (Get-Command $script:scriptPath).Parameters
            $params.ContainsKey('Head') | Should -Be $true
        }
    }

    Context "When validating skill delegation" {
        It "Skill script should exist" {
            Test-Path $script:skillPath | Should -Be $true
        }

        It "Skill should have valid PowerShell syntax" {
            {
                $null = [System.Management.Automation.PSParser]::Tokenize(
                    (Get-Content $script:skillPath -Raw),
                    [ref]$null
                )
            } | Should -Not -Throw
        }

        It "Skill should test conventional commit format" {
            $content = Get-Content $script:skillPath -Raw
            $content | Should -Match "Test-ConventionalCommit"
        }

        It "Skill should document exit codes" {
            $content = Get-Content $script:skillPath -Raw
            $content | Should -Match "Exit codes:"
            $content | Should -Match "0 = Success"
            $content | Should -Match "1 = Validation failure"
            $content | Should -Match "2 = Usage/environment error"
        }
    }

    Context "When SkipValidation is used" {
        It "Should require audit trail with AuditReason" {
            # This test validates the skill logic
            $content = Get-Content $script:skillPath -Raw
            $content | Should -Match "SkipValidation.*AuditReason"
            $content | Should -Match "Write-AuditLog"
        }

        It "Should use cross-platform username in audit log" {
            # Verify fix for cursor[bot] issue #2640305975
            $content = Get-Content $script:skillPath -Raw
            # Should check both env:USERNAME (Windows) and env:USER (Linux/macOS)
            $content | Should -Match '\$env:USERNAME.*\$env:USER'
            # Should have fallback to whoami
            $content | Should -Match 'whoami'
        }
    }
}
