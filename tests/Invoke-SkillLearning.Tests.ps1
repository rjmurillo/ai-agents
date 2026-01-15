#Requires -Modules Pester

BeforeAll {
    Import-Module "$PSScriptRoot/TestUtilities.psm1" -Force

    $Script:HelpersModulePath = Join-Path $PSScriptRoot ".." ".claude" "hooks" "Stop" "SkillLearning.Helpers.psm1"
    Import-Module $Script:HelpersModulePath -Force

    $Script:SkillPatternMap = Get-DefaultSkillPatternMap
    $Script:SlashCommandSkillMap = Get-DefaultSlashCommandSkillMap
}

AfterAll {
    Remove-Module SkillLearning.Helpers -ErrorAction SilentlyContinue
}

Describe "Detect-SkillUsage" {
    It "detects explicit .claude skill references" {
        $messages = @(
            [pscustomobject]@{ role = 'user'; content = 'Working against .claude/skills/github helper today.' }
        )

        $result = Detect-SkillUsage -Messages $messages -SkillPatternMap $Script:SkillPatternMap -SlashCommandSkillMap $Script:SlashCommandSkillMap

        $result.ContainsKey('github') | Should -BeTrue
    }

    It "detects mapped slash commands" {
        $messages = @(
            [pscustomobject]@{ role = 'assistant'; content = 'Try running /pr-review to load reviewers.' }
        )

        $result = Detect-SkillUsage -Messages $messages -SkillPatternMap $Script:SkillPatternMap -SlashCommandSkillMap $Script:SlashCommandSkillMap

        $result['github'] | Should -BeGreaterThan 0
    }

    It "requires repeated keyword matches before counting" {
        $messages = @(
            [pscustomobject]@{ role = 'assistant'; content = 'memory-first workflow keeps us aligned.' },
            [pscustomobject]@{ role = 'user'; content = 'yes, memory-first instructions prevent drift.' }
        )

        $result = Detect-SkillUsage -Messages $messages -SkillPatternMap $Script:SkillPatternMap -SlashCommandSkillMap $Script:SlashCommandSkillMap

        $result['memory'] | Should -BeGreaterThan 1
    }
}

Describe "Extract-Learnings" {
    It "captures high confidence corrections when the user rejects output" {
        $messages = @(
            [pscustomobject]@{ role = 'assistant'; content = 'Use the github skill template for this change.' },
            [pscustomobject]@{ role = 'user'; content = 'No, that is wrong. Never do that again.' }
        )

        $result = Extract-Learnings -Messages $messages -SkillName 'github' -SkillPatternMap $Script:SkillPatternMap

        ($result.High | Where-Object { $_.Type -eq 'correction' }).Count | Should -BeGreaterThan 0
    }

    It "captures edge case questions as medium confidence learnings" {
        $messages = @(
            [pscustomobject]@{ role = 'assistant'; content = 'github skill handles pull requests.' },
            [pscustomobject]@{ role = 'user'; content = 'What if the branch has no reviewers?' }
        )

        $result = Extract-Learnings -Messages $messages -SkillName 'github' -SkillPatternMap $Script:SkillPatternMap

        ($result.Med | Where-Object { $_.Type -eq 'edge_case' }).Count | Should -BeGreaterThan 0
    }

    It "tracks command patterns as low confidence learnings" {
        $messages = @(
            [pscustomobject]@{ role = 'assistant'; content = 'Use the github helpers to stage changes.' },
            [pscustomobject]@{ role = 'user'; content = 'pwsh ./scripts/Sync-Review.ps1' }
        )

        $result = Extract-Learnings -Messages $messages -SkillName 'github' -SkillPatternMap $Script:SkillPatternMap

        $result.Low | Should -Not -BeNullOrEmpty
        $result.Low[0].Type | Should -Be 'command_pattern'
    }
}

Describe "Update-SkillMemory" {
    BeforeEach {
        $Script:TempProjectDir = Join-Path ([IO.Path]::GetTempPath()) ("skill-learning-test-" + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $Script:TempProjectDir -Force | Out-Null
    }

    AfterEach {
        if (Test-Path $Script:TempProjectDir) {
            Remove-Item -Path $Script:TempProjectDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It "creates sidecar file and appends learnings" {
        $learnings = @{
            High = @(@{ Type = 'correction'; Source = 'Fix the broken detection'; Context = 'assistant output' })
            Med  = @(
                @{ Type = 'preference'; Source = 'Prefer ready templates'; Context = 'assistant output' },
                @{ Type = 'edge_case'; Source = 'Ensure we handle missing files'; Context = 'assistant output' }
            )
            Low  = @(@{ Type = 'command_pattern'; Source = 'gh pr view'; Context = 'assistant output' })
        }

        $result = Update-SkillMemory -ProjectDir $Script:TempProjectDir -SkillName 'github' -Learnings $learnings -SessionId 'test-session-1'
        $result | Should -BeTrue

        $memoryPath = Join-Path $Script:TempProjectDir ".serena/memories/github-skill-sidecar-learnings.md"
        Test-Path $memoryPath | Should -BeTrue

        $content = Get-Content $memoryPath -Raw
        $content | Should -Match '\*\*Sessions Analyzed\*\*: 1'
        $content | Should -Match '- Fix the broken detection'
        $content | Should -Match '- Prefer ready templates'
        $content | Should -Match '- Ensure we handle missing files'
        $content | Should -Match '- gh pr view'
    }

    It "prevents path traversal writes" {
        $emptyLearnings = @{ High = @(); Med = @(); Low = @() }

        Mock -ModuleName SkillLearning.Helpers -CommandName Get-SkillSlug -MockWith { '..\\..\\..\\escape' }

        $result = Update-SkillMemory -ProjectDir $Script:TempProjectDir -SkillName 'github' -Learnings $emptyLearnings -SessionId 'test-session-2'
        $result | Should -BeFalse
    }
}
