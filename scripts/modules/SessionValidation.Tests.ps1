#Requires -Modules Pester

BeforeAll {
    $modulePath = Join-Path $PSScriptRoot "SessionValidation.psm1"
    Import-Module $modulePath -Force

    function Assert-StandardContract {
        param($result)
        ($result.Keys | Sort-Object) | Should -Be @('Errors','FixableIssues','IsValid','Warnings')
    }
}

Describe "Test-RequiredSections" {
    It "returns standardized contract" {
        $content = @"
## Session Start
## Session End
## Evidence
"@
        $result = Test-RequiredSections -SessionLogContent $content

        Assert-StandardContract $result
    }

    It "returns valid when all sections are present" {
        $content = @"
## Session Start
## Session End
## Evidence
"@
        $result = Test-RequiredSections -SessionLogContent $content

        Assert-StandardContract $result
        $result.IsValid | Should -BeTrue
        $result.Errors | Should -BeNullOrEmpty
    }

    It "returns missing sections when absent" {
        $content = "## Session Start"
        $result = Test-RequiredSections -SessionLogContent $content

        $result.IsValid | Should -BeFalse
        Assert-StandardContract $result
        ($result.Errors -join ' ') | Should -Match "Missing required sections"
    }
}

Describe "Test-TableStructure" {
    It "returns standardized contract" {
        $table = @(
            '| Req | Step | Status | Evidence |',
            '|-----|------|--------|----------|',
            '| MUST | Do thing | [x] | proof |'
        )

        $result = Test-TableStructure -TableLines $table

        Assert-StandardContract $result
    }

    It "passes with well-formed table" {
        $table = @(
            '| Req | Step | Status | Evidence |',
            '|-----|------|--------|----------|',
            '| MUST | Do thing | [x] | proof |'
        )

        $result = Test-TableStructure -TableLines $table

        Assert-StandardContract $result
        $result.IsValid | Should -BeTrue
        $result.Errors | Should -BeNullOrEmpty
        $result.FixableIssues | Should -BeNullOrEmpty
    }

    It "fails when header is missing" {
        $table = @(
            '|-----|------|--------|----------|',
            '| MUST | Do thing | [ ] | - |'
        )

        $result = Test-TableStructure -TableLines $table

        Assert-StandardContract $result
        $result.IsValid | Should -BeFalse
        $result.Errors | Should -Not -BeNullOrEmpty
    }
}

Describe "Test-PathNormalization" {
    It "returns standardized contract" {
        $content = "[file.md](docs/file.md)"
        $result = Test-PathNormalization -SessionLogContent $content

        Assert-StandardContract $result
    }

    It "accepts repo-relative paths" {
        $content = "[file.md](docs/file.md)"
        $result = Test-PathNormalization -SessionLogContent $content

        Assert-StandardContract $result
        $result.IsValid | Should -BeTrue
        $result.Errors | Should -BeNullOrEmpty
        $result.FixableIssues | Should -BeNullOrEmpty
    }

    It "rejects absolute paths" {
        $content = "See /home/user/file.md for details"
        $result = Test-PathNormalization -SessionLogContent $content

        Assert-StandardContract $result
        $result.IsValid | Should -BeFalse
        $result.Errors | Should -HaveCount 1
        $result.FixableIssues | Should -HaveCount 1
    }
}

Describe "Test-CommitSHAFormat" {
    It "returns standardized contract" {
        $result = Test-CommitSHAFormat -CommitSHA "abc1234"

        Assert-StandardContract $result
    }

    It "accepts valid short SHA" {
        $result = Test-CommitSHAFormat -CommitSHA "abc1234"

        Assert-StandardContract $result
        $result.IsValid | Should -BeTrue
    }

    It "accepts valid long SHA" {
        $result = Test-CommitSHAFormat -CommitSHA "abc1234567890abcdef1234567890abcdef1234"

        Assert-StandardContract $result
        $result.IsValid | Should -BeTrue
    }

    It "rejects SHA with subject" {
        $result = Test-CommitSHAFormat -CommitSHA "abc1234 Fix bug"

        Assert-StandardContract $result
        $result.IsValid | Should -BeFalse
        $result.Errors | Should -HaveCount 1
        $result.Errors[0] | Should -Match "subject line"
    }

    It "rejects empty SHA" {
        $result = Test-CommitSHAFormat -CommitSHA ""

        Assert-StandardContract $result
        $result.IsValid | Should -BeFalse
    }
}

Describe "Test-EvidencePopulation" {
    It "returns standardized contract" {
        $fields = @{ Branch = "main"; Commit = "abc1234"; Status = "clean" }
        $result = Test-EvidencePopulation -EvidenceFields $fields

        Assert-StandardContract $result
    }

    It "accepts populated evidence" {
        $fields = @{ Branch = "main"; Commit = "abc1234"; Status = "clean" }
        $result = Test-EvidencePopulation -EvidenceFields $fields

        Assert-StandardContract $result
        $result.IsValid | Should -BeTrue
    }

    It "flags placeholders and empties" {
        $fields = @{ Branch = "[branch]"; Commit = ""; Status = "-" }
        $result = Test-EvidencePopulation -EvidenceFields $fields

        Assert-StandardContract $result
        $result.IsValid | Should -BeFalse
        $result.Errors.Count | Should -BeGreaterThan 0
    }
}

Describe "Test-TemplateStructure" {
    It "returns standardized contract" {
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

        Assert-StandardContract $result
    }

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

        Assert-StandardContract $result
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

        Assert-StandardContract $result
        $result.IsValid | Should -BeFalse
        $result.Warnings | Should -Not -BeNullOrEmpty
    }
}

Describe "Test-EvidenceFields" {
    It "returns standardized contract" {
        $sessionLog = @"
## Evidence
- Branch: feat/test
- Commit: abc1234
- Status: clean
"@
        $gitInfo = @{ RepoRoot = "/repo"; Branch = "feat/test"; Commit = "abc1234"; Status = "clean" }

        $result = Test-EvidenceFields -SessionLog $sessionLog -GitInfo $gitInfo

        Assert-StandardContract $result
    }

    It "passes when evidence is valid" {
        $sessionLog = @"
## Evidence
- Branch: feat/test
- Commit: abc1234
- Status: clean
"@
        $gitInfo = @{ RepoRoot = "/repo"; Branch = "feat/test"; Commit = "abc1234"; Status = "clean" }

        $result = Test-EvidenceFields -SessionLog $sessionLog -GitInfo $gitInfo

        Assert-StandardContract $result
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

    Assert-StandardContract $result
        $result.IsValid | Should -BeFalse
        $result.FixableIssues | Should -Not -BeNullOrEmpty
        $result.FixableIssues[0].Type | Should -Be "PathNormalization"
    }
}

Describe "Test-SessionLogExists" {
    It "returns standardized contract" {
        $path = Join-Path $TestDrive "missing/2026-01-05-session-1.md"

        $result = Test-SessionLogExists -FilePath $path

        Assert-StandardContract $result
    }

    It "fails when file is missing" {
        $path = Join-Path $TestDrive "missing/2026-01-05-session-1.md"

        $result = Test-SessionLogExists -FilePath $path

        Assert-StandardContract $result
        $result.IsValid | Should -BeFalse
        $result.Errors | Should -Not -BeNullOrEmpty
    }

    It "passes with valid naming" {
        $sessionsDir = Join-Path $TestDrive "sessions"
        New-Item -ItemType Directory -Path $sessionsDir -Force | Out-Null
        $path = Join-Path $sessionsDir "2026-01-05-session-1.md"
        Set-Content -Path $path -Value "## Session Start"

        $result = Test-SessionLogExists -FilePath $path

        Assert-StandardContract $result
        $result.IsValid | Should -BeTrue
        $result.Errors | Should -BeNullOrEmpty
    }

    It "fails with invalid filename" {
        $sessionsDir = Join-Path $TestDrive "sessions-badname"
        New-Item -ItemType Directory -Path $sessionsDir -Force | Out-Null
        $path = Join-Path $sessionsDir "session.md"
        Set-Content -Path $path -Value "## Session Start"

        $result = Test-SessionLogExists -FilePath $path

    Assert-StandardContract $result
        $result.IsValid | Should -BeFalse
        $result.Errors | Should -Not -BeNullOrEmpty
        $result.Errors[0] | Should -Match "naming violation"
    }
}

Describe "Test-ProtocolComplianceSection" {
    It "returns standardized contract" {
        $content = "## Protocol Compliance"
        $result = Test-ProtocolComplianceSection -Content $content

        Assert-StandardContract $result
    }

    It "passes when start and end checklists exist" {
        $content = @"
## Protocol Compliance
Session Start - COMPLETE ALL
Session End - COMPLETE ALL
"@

        $result = Test-ProtocolComplianceSection -Content $content

        Assert-StandardContract $result
        $result.IsValid | Should -BeTrue
        $result.Errors | Should -BeNullOrEmpty
    }

    It "fails when headers are missing" {
        $content = "## Protocol Compliance"

        $result = Test-ProtocolComplianceSection -Content $content

        Assert-StandardContract $result
        $result.Errors | Should -Not -BeNullOrEmpty
    }
}

Describe "Test-MustRequirements" {
    It "returns standardized contract" {
        $content = @"
| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Do thing | [ ] | - |
"@

        $result = Test-MustRequirements -Content $content

        Assert-StandardContract $result
    }

    It "fails when MUST items are unchecked" {
        $content = @"
| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Do thing | [ ] | - |
| MUST | Done | [x] | proof |
"@

        $result = Test-MustRequirements -Content $content

        Assert-StandardContract $result
        $result.IsValid | Should -BeFalse
        $result.Errors | Should -Not -BeNullOrEmpty
    }

    It "passes when all MUST items are checked" {
        $content = @"
| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Do thing | [x] | proof |
| MUST | Done | [x] | proof |
"@

        $result = Test-MustRequirements -Content $content

        Assert-StandardContract $result
        $result.IsValid | Should -BeTrue
        $result.Errors | Should -BeNullOrEmpty
    }

    It "handles uppercase status via fallback" {
        $content = @"
| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Do thing | [X] | proof |
"@

        $result = Test-MustRequirements -Content $content

        Assert-StandardContract $result
        $result.IsValid | Should -BeTrue
        $result.Errors | Should -BeNullOrEmpty
    }
}

Describe "Test-MustNotRequirements" {
    It "returns standardized contract" {
        $content = @"
| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST NOT | Update HANDOFF | [ ] | - |
"@

        $result = Test-MustNotRequirements -Content $content

        Assert-StandardContract $result
    }

    It "fails when MUST NOT is unchecked" {
        $content = @"
| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST NOT | Update HANDOFF | [ ] | - |
"@

        $result = Test-MustNotRequirements -Content $content

        Assert-StandardContract $result
        $result.IsValid | Should -BeFalse
        $result.Errors | Should -Not -BeNullOrEmpty
    }

    It "passes when all MUST NOT items are verified" {
        $content = @"
| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST NOT | Update HANDOFF | [x] | - |
"@

        $result = Test-MustNotRequirements -Content $content

        Assert-StandardContract $result
        $result.IsValid | Should -BeTrue
        $result.Errors | Should -BeNullOrEmpty
    }

    It "handles uppercase status via fallback" {
        $content = @"
| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST NOT | Update HANDOFF | [X] | - |
"@

        $result = Test-MustNotRequirements -Content $content

        Assert-StandardContract $result
        $result.IsValid | Should -BeTrue
        $result.Errors | Should -BeNullOrEmpty
    }
}
 
Describe "Test-HandoffUpdated" {
    It "returns standardized contract" {
        $repo = Join-Path $TestDrive "repo"
        $sessionsDir = Join-Path $repo ".agents/sessions"
        New-Item -ItemType Directory -Path $sessionsDir -Force | Out-Null
        $sessionPath = Join-Path $sessionsDir "2024-01-02-session-1.md"
        Set-Content -Path $sessionPath -Value "# session"

        $result = Test-HandoffUpdated -SessionPath $sessionPath -BasePath $repo

        Assert-StandardContract $result
    }

    It "passes when HANDOFF.md is older than session" {
        $repo = Join-Path $TestDrive "repo"
        $sessionsDir = Join-Path $repo ".agents/sessions"
        New-Item -ItemType Directory -Path $sessionsDir -Force | Out-Null
        $handoffPath = Join-Path $repo ".agents/HANDOFF.md"
        New-Item -ItemType File -Path $handoffPath -Force | Out-Null
        $sessionPath = Join-Path $sessionsDir "2024-01-02-session-1.md"
        Set-Content -Path $sessionPath -Value "# session"
        (Get-Item -LiteralPath $handoffPath).LastWriteTime = (Get-Date '2023-12-31')

        $result = Test-HandoffUpdated -SessionPath $sessionPath -BasePath $repo

        Assert-StandardContract $result
        $result.IsValid | Should -BeTrue
        $result.Errors | Should -BeNullOrEmpty
        $result.FixableIssues | Should -BeNullOrEmpty
    }

    It "fails when HANDOFF.md is newer than session" {
        $repo = Join-Path $TestDrive "repo-newer"
        $sessionsDir = Join-Path $repo ".agents/sessions"
        New-Item -ItemType Directory -Path $sessionsDir -Force | Out-Null
        $handoffPath = Join-Path $repo ".agents/HANDOFF.md"
        New-Item -ItemType File -Path $handoffPath -Force | Out-Null
        $sessionPath = Join-Path $sessionsDir "2024-01-02-session-1.md"
        Set-Content -Path $sessionPath -Value "# session"
        (Get-Item -LiteralPath $handoffPath).LastWriteTime = (Get-Date '2024-01-03')

        $result = Test-HandoffUpdated -SessionPath $sessionPath -BasePath $repo

        Assert-StandardContract $result
        $result.IsValid | Should -BeFalse
        $result.Errors | Should -Not -BeNullOrEmpty
    }

    It "fails when origin/main is missing (shallow clone path)" {
        $repo = Join-Path $TestDrive "repo-shallow"
        New-Item -ItemType Directory -Path $repo -Force | Out-Null
        git -C $repo init | Out-Null

        $sessionsDir = Join-Path $repo ".agents/sessions"
        New-Item -ItemType Directory -Path $sessionsDir -Force | Out-Null
        $handoffPath = Join-Path $repo ".agents/HANDOFF.md"
        New-Item -ItemType File -Path $handoffPath -Force | Out-Null
        $sessionPath = Join-Path $sessionsDir "2024-01-02-session-1.md"
        Set-Content -Path $sessionPath -Value "# session"

        $result = Test-HandoffUpdated -SessionPath $sessionPath -BasePath $repo

        Assert-StandardContract $result
        $result.IsValid | Should -BeFalse
        ($result.Errors -join ' ') | Should -Match "shallow git checkout"
    }

    It "falls back to timestamp when git diff fails" {
        $repo = Join-Path $TestDrive "repo-diff-fail"
        $sessionsDir = Join-Path $repo ".agents/sessions"
        New-Item -ItemType Directory -Path $sessionsDir -Force | Out-Null
        $handoffPath = Join-Path $repo ".agents/HANDOFF.md"
        New-Item -ItemType File -Path $handoffPath -Force | Out-Null
        $sessionPath = Join-Path $sessionsDir "2024-01-02-session-1.md"
        Set-Content -Path $sessionPath -Value "# session"
        (Get-Item -LiteralPath $handoffPath).LastWriteTime = (Get-Date '2024-01-01')

        git -C $repo init | Out-Null

        $realGitPath = (Get-Command git).Source
        function global:git {
            param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)

            if ($Args[0] -eq 'rev-parse' -and $Args[1] -eq '--git-dir') { $global:LASTEXITCODE = 0; '.git'; return }
            if ($Args[0] -eq 'rev-parse' -and $Args[1] -eq '--verify' -and $Args[2] -eq 'origin/main') { $global:LASTEXITCODE = 0; 'origin/main'; return }
            if ($Args[0] -eq 'diff') { $global:LASTEXITCODE = 1; 'simulated diff failure'; return }

            & $realGitPath @Args
            $global:LASTEXITCODE = $LASTEXITCODE
        }
        try {
            $result = Test-HandoffUpdated -SessionPath $sessionPath -BasePath $repo

            Assert-StandardContract $result
            $result.IsValid | Should -BeTrue
            ($result.Warnings -join ' ') | Should -Match 'Git diff failed'
            $result.Errors | Should -BeNullOrEmpty
        }
        finally {
            Remove-Item Function:git -ErrorAction SilentlyContinue
        }
    }
}

Describe "Test-ShouldRequirements" {
    It "returns standardized contract" {
        $content = @"
| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| SHOULD | Capture metric | [ ] | - |
"@

        $result = Test-ShouldRequirements -Content $content

        Assert-StandardContract $result
    }

    It "returns warnings without failing" {
        $content = @"
| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| SHOULD | Capture metric | [ ] | - |
"@

        $result = Test-ShouldRequirements -Content $content

        Assert-StandardContract $result
        $result.IsValid | Should -BeTrue
        $result.Warnings.Count | Should -BeGreaterThan 0
    }
}

Describe "Test-GitCommitEvidence" {
    It "returns standardized contract" {
        $content = "commit: abc1234"
        $result = Test-GitCommitEvidence -Content $content

        Assert-StandardContract $result
    }

    It "passes with valid commit evidence" {
        $content = @"
commit: abc1234
"@

        $result = Test-GitCommitEvidence -Content $content

        Assert-StandardContract $result
        $result.IsValid | Should -BeTrue
        $result.Errors | Should -BeNullOrEmpty
    }

    It "fails when commit is missing" {
        $content = "no commit here"

        $result = Test-GitCommitEvidence -Content $content

        Assert-StandardContract $result
        $result.IsValid | Should -BeFalse
        $result.Errors | Should -Not -BeNullOrEmpty
    }

    It "fails when commit SHA format is invalid" {
        $content = @"
commit: abc1234Z
"@

        $result = Test-GitCommitEvidence -Content $content

        Assert-StandardContract $result
        $result.IsValid | Should -BeFalse
        ($result.Errors -join ' ') | Should -Match 'format invalid'
    }
}

Describe "Test-SessionLogCompleteness" {
    It "returns standardized contract" {
        $content = "## Session Start"
        $result = Test-SessionLogCompleteness -Content $content

        Assert-StandardContract $result
    }

    It "flags missing sections" {
        $content = "## Session Start"

        $result = Test-SessionLogCompleteness -Content $content

        Assert-StandardContract $result
        $result.IsValid | Should -BeFalse
        $result.Errors | Should -Not -BeNullOrEmpty
    }

    It "passes when all expected sections exist" {
        $content = @"
## Session Info
details
## Protocol Compliance
Session Start - COMPLETE ALL
Session End - COMPLETE ALL
## Session Start
| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Start work | [x] | - |
## Work Log
completed items
## Session End
| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Finish work | [x] | - |
## Evidence
Commit: abc1234
"@

        $result = Test-SessionLogCompleteness -Content $content

        Assert-StandardContract $result
        $result.IsValid | Should -BeTrue
        $result.Errors | Should -BeNullOrEmpty
        $result.Warnings | Should -BeNullOrEmpty
        $result.FixableIssues | Should -BeNullOrEmpty
    }
}

Describe "Invoke-FullValidation" {
    It "returns standardized contract" {
        $sessionPath = Join-Path $TestDrive "session.md"
        Set-Content -Path $sessionPath -Value "## Session Start"

        $result = Invoke-FullValidation -SessionLogPath $sessionPath -RepoRoot (Join-Path $TestDrive "missing-repo")

        Assert-StandardContract $result
    }

    It "fails when validation script is missing" {
        $sessionPath = Join-Path $TestDrive "session.md"
        Set-Content -Path $sessionPath -Value "## Session Start"

        $result = Invoke-FullValidation -SessionLogPath $sessionPath -RepoRoot (Join-Path $TestDrive "missing-repo")

        Assert-StandardContract $result
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

        Assert-StandardContract $result
        $result.IsValid | Should -BeTrue
        $result.Errors | Should -BeNullOrEmpty
    }
}
