#Requires -Modules Pester

BeforeAll {
    $modulePath = Join-Path $PSScriptRoot "SessionValidation.psm1"
    Import-Module $modulePath -Force
}

Describe "Test-RequiredSections" {
    It "returns valid when all sections are present" {
        $content = @"
## Session Start
## Session End
## Evidence
"@
        $result = Test-RequiredSections -SessionLogContent $content

        $result.IsValid | Should -BeTrue
        $result.MissingSections | Should -BeNullOrEmpty
    }

    It "returns missing sections when absent" {
        $content = "## Session Start"
        $result = Test-RequiredSections -SessionLogContent $content

        $result.IsValid | Should -BeFalse
        $result.MissingSections | Should -Contain "## Session End"
    }
}

Describe "Test-TableStructure" {
    It "passes with well-formed table" {
        $table = @(
            '| Req | Step | Status | Evidence |',
            '|-----|------|--------|----------|',
            '| MUST | Do thing | [x] | proof |'
        )

        $result = Test-TableStructure -TableLines $table

        $result.IsValid | Should -BeTrue
        $result.Errors | Should -BeNullOrEmpty
        $result.ParsedRows.Count | Should -Be 1
    }

    It "fails when header is missing" {
        $table = @(
            '|-----|------|--------|----------|',
            '| MUST | Do thing | [ ] | - |'
        )

        $result = Test-TableStructure -TableLines $table

        $result.IsValid | Should -BeFalse
        $result.Errors | Should -Not -BeNullOrEmpty
    }
}

Describe "Test-PathNormalization" {
    It "accepts repo-relative paths" {
        $content = "[file.md](docs/file.md)"
        $result = Test-PathNormalization -SessionLogContent $content

        $result.IsValid | Should -BeTrue
        $result.AbsolutePaths | Should -BeNullOrEmpty
    }

    It "rejects absolute paths" {
        $content = "See /home/user/file.md for details"
        $result = Test-PathNormalization -SessionLogContent $content

        $result.IsValid | Should -BeFalse
        $result.AbsolutePaths.Count | Should -BeGreaterThan 0
    }
}

Describe "Test-CommitSHAFormat" {
    It "accepts valid short SHA" {
        $result = Test-CommitSHAFormat -CommitSHA "abc1234"
        $result.IsValid | Should -BeTrue
    }

    It "accepts valid long SHA" {
        $result = Test-CommitSHAFormat -CommitSHA "abc1234567890abcdef1234567890abcdef1234"
        $result.IsValid | Should -BeTrue
    }

    It "rejects SHA with subject" {
        $result = Test-CommitSHAFormat -CommitSHA "abc1234 Fix bug"
        $result.IsValid | Should -BeFalse
        $result.Error | Should -Match "subject line"
    }

    It "rejects empty SHA" {
        $result = Test-CommitSHAFormat -CommitSHA ""
        $result.IsValid | Should -BeFalse
    }
}

Describe "Test-EvidencePopulation" {
    It "accepts populated evidence" {
        $fields = @{ Branch = "main"; Commit = "abc1234"; Status = "clean" }
        $result = Test-EvidencePopulation -EvidenceFields $fields

        $result.IsValid | Should -BeTrue
    }

    It "flags placeholders and empties" {
        $fields = @{ Branch = "[branch]"; Commit = ""; Status = "-" }
        $result = Test-EvidencePopulation -EvidenceFields $fields

        $result.IsValid | Should -BeFalse
        $result.Errors.Count | Should -BeGreaterThan 0
    }
}

Describe "Test-TemplateStructure" {
    It "passes when sections and tables exist" {
        $template = @"
## Session Start
| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Start work | [ ] | - |

## Session End
| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Finish work | [ ] | - |

## Evidence
| Field | Value |
|-------|-------|
| Branch | main |
"@

        $result = Test-TemplateStructure -Template $template

        $result.IsValid | Should -BeTrue
        $result.Errors | Should -BeNullOrEmpty
    }

    It "warns when evidence table missing" {
        $template = @"
## Session Start
| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Start work | [ ] | - |

## Session End
| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Finish work | [ ] | - |
"@

        $result = Test-TemplateStructure -Template $template

        $result.IsValid | Should -BeFalse
        $result.Warnings | Should -Not -BeNullOrEmpty
    }
}

Describe "Test-EvidenceFields" {
    It "passes when evidence is valid" {
        $sessionLog = @"
## Evidence
- Branch: feat/test
- Commit: abc1234
- Status: clean
"@
        $gitInfo = @{ RepoRoot = "/repo"; Branch = "feat/test"; Commit = "abc1234"; Status = "clean" }

        $result = Test-EvidenceFields -SessionLog $sessionLog -GitInfo $gitInfo

        $result.IsValid | Should -BeTrue
        $result.FixableIssues | Should -BeNullOrEmpty
    }

    It "returns fixable issues for absolute paths" {
        $sessionLog = @"
## Evidence
- File: C:\Users\user\repo\file.md
- Commit: abc1234 Fix bug
- Branch: main
- Status: clean
"@
        $gitInfo = @{ RepoRoot = "/repo"; Branch = "main"; Commit = "abc1234"; Status = "clean" }

        $result = Test-EvidenceFields -SessionLog $sessionLog -GitInfo $gitInfo

        $result.IsValid | Should -BeFalse
        $result.FixableIssues | Should -Not -BeNullOrEmpty
        $result.FixableIssues[0].Type | Should -Be "PathNormalization"
    }
}

Describe "Invoke-FullValidation" {
    It "fails when validation script is missing" {
        $sessionPath = Join-Path $TestDrive "session.md"
        Set-Content -Path $sessionPath -Value "## Session Start"

        $result = Invoke-FullValidation -SessionLogPath $sessionPath -RepoRoot (Join-Path $TestDrive "missing-repo")

        $result.IsValid | Should -BeFalse
        $result.Errors | Should -Not -BeNullOrEmpty
    }

    It "passes when validation script returns success" {
        $repoRoot = Join-Path $TestDrive "repo"
        $scriptDir = Join-Path $repoRoot "scripts"
        New-Item -ItemType Directory -Path $scriptDir -Force | Out-Null

        $validatorPath = Join-Path $scriptDir "Validate-SessionProtocol.ps1"
        @"
param([string]`$SessionPath,[string]`$Format)
Write-Output "ok"
"@ | Set-Content -Path $validatorPath -NoNewline

        $sessionPath = Join-Path $TestDrive "session.md"
        Set-Content -Path $sessionPath -Value "## Session Start"

        $result = Invoke-FullValidation -SessionLogPath $sessionPath -RepoRoot $repoRoot

        $result.IsValid | Should -BeTrue
        $result.Errors | Should -BeNullOrEmpty
    }
}
