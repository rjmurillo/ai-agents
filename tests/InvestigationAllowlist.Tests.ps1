#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for InvestigationAllowlist.psm1 shared module.

.DESCRIPTION
    Tests the canonical investigation-only allowlist patterns, display paths,
    and file matching logic per ADR-034.

.NOTES
    Issue #840: Test coverage for shared allowlist module.
#>

BeforeAll {
    Import-Module (Join-Path $PSScriptRoot '../scripts/modules/InvestigationAllowlist.psm1') -Force
}

AfterAll {
    Remove-Module InvestigationAllowlist -Force -ErrorAction SilentlyContinue
}

Describe 'Get-InvestigationAllowlist' {

    Context 'Pattern Count' {
        It 'Returns exactly 9 canonical patterns' {
            $patterns = Get-InvestigationAllowlist
            $patterns.Count | Should -Be 9
        }
    }

    Context 'Canonical Patterns Present' {
        BeforeAll {
            $Script:Patterns = Get-InvestigationAllowlist
        }

        It 'Contains .agents/sessions/ pattern' {
            $Script:Patterns | Should -Contain '^\.agents/sessions/'
        }

        It 'Contains .agents/analysis/ pattern' {
            $Script:Patterns | Should -Contain '^\.agents/analysis/'
        }

        It 'Contains .agents/retrospective/ pattern' {
            $Script:Patterns | Should -Contain '^\.agents/retrospective/'
        }

        It 'Contains .serena/memories pattern with anchoring' {
            $Script:Patterns | Should -Contain '^\.serena/memories($|/)'
        }

        It 'Contains .agents/security/ pattern' {
            $Script:Patterns | Should -Contain '^\.agents/security/'
        }

        It 'Contains .agents/memory/ pattern' {
            $Script:Patterns | Should -Contain '^\.agents/memory/'
        }

        It 'Contains .agents/architecture/REVIEW- pattern' {
            $Script:Patterns | Should -Contain '^\.agents/architecture/REVIEW-'
        }

        It 'Contains .agents/critique/ pattern' {
            $Script:Patterns | Should -Contain '^\.agents/critique/'
        }

        It 'Contains .agents/memory/episodes/ pattern' {
            $Script:Patterns | Should -Contain '^\.agents/memory/episodes/'
        }
    }
}

Describe 'Get-InvestigationAllowlistDisplay' {

    It 'Returns display-friendly paths' {
        $display = Get-InvestigationAllowlistDisplay
        $display.Count | Should -Be 9
        $display | Should -Contain '.agents/sessions/'
        $display | Should -Contain '.serena/memories/'
    }
}

Describe 'Test-FileMatchesAllowlist' {

    Context 'Allowed Files' {
        It 'Matches session log files' {
            Test-FileMatchesAllowlist -FilePath '.agents/sessions/2026-02-07-session-1180.json' | Should -BeTrue
        }

        It 'Matches analysis files' {
            Test-FileMatchesAllowlist -FilePath '.agents/analysis/research-findings.md' | Should -BeTrue
        }

        It 'Matches retrospective files' {
            Test-FileMatchesAllowlist -FilePath '.agents/retrospective/session-learnings.md' | Should -BeTrue
        }

        It 'Matches Serena memory files' {
            Test-FileMatchesAllowlist -FilePath '.serena/memories/context.md' | Should -BeTrue
        }

        It 'Matches .serena/memories directory itself' {
            Test-FileMatchesAllowlist -FilePath '.serena/memories' | Should -BeTrue
        }

        It 'Matches security assessment files' {
            Test-FileMatchesAllowlist -FilePath '.agents/security/threat-review.md' | Should -BeTrue
        }

        It 'Matches memory infrastructure files' {
            Test-FileMatchesAllowlist -FilePath '.agents/memory/causality/causal-graph.json' | Should -BeTrue
        }

        It 'Matches ADR review artifacts' {
            Test-FileMatchesAllowlist -FilePath '.agents/architecture/REVIEW-ADR-042.md' | Should -BeTrue
        }

        It 'Matches critique debate logs' {
            Test-FileMatchesAllowlist -FilePath '.agents/critique/debate-log.md' | Should -BeTrue
        }

        It 'Matches memory episode extractions' {
            Test-FileMatchesAllowlist -FilePath '.agents/memory/episodes/episode-001.json' | Should -BeTrue
        }
    }

    Context 'Rejected Files' {
        It 'Rejects code files' {
            Test-FileMatchesAllowlist -FilePath 'scripts/Validate-Session.ps1' | Should -BeFalse
        }

        It 'Rejects workflow files' {
            Test-FileMatchesAllowlist -FilePath '.github/workflows/ci.yml' | Should -BeFalse
        }

        It 'Rejects planning documents' {
            Test-FileMatchesAllowlist -FilePath '.agents/planning/feature-prd.md' | Should -BeFalse
        }

        It 'Rejects non-REVIEW architecture files' {
            Test-FileMatchesAllowlist -FilePath '.agents/architecture/ADR-042.md' | Should -BeFalse
        }

        It 'Rejects .agents/sessions-evil/ path traversal' {
            Test-FileMatchesAllowlist -FilePath '.agents/sessions-evil/malicious.md' | Should -BeFalse
        }

        It 'Rejects .serena/memoriesX/ path traversal' {
            Test-FileMatchesAllowlist -FilePath '.serena/memoriesX/evil.md' | Should -BeFalse
        }

        It 'Rejects agent prompt files' {
            Test-FileMatchesAllowlist -FilePath '.claude/agents/analyst.md' | Should -BeFalse
        }

        It 'Rejects skill files' {
            Test-FileMatchesAllowlist -FilePath '.claude/skills/session/scripts/Test.ps1' | Should -BeFalse
        }
    }

    Context 'Path Normalization' {
        It 'Normalizes Windows backslashes to forward slashes' {
            Test-FileMatchesAllowlist -FilePath '.agents\sessions\2026-02-07-session-01.json' | Should -BeTrue
        }

        It 'Handles mixed path separators' {
            Test-FileMatchesAllowlist -FilePath '.agents/sessions\nested\file.md' | Should -BeTrue
        }
    }
}

Describe 'Module Exports' {
    It 'Exports Get-InvestigationAllowlist' {
        Get-Command Get-InvestigationAllowlist -Module InvestigationAllowlist | Should -Not -BeNullOrEmpty
    }

    It 'Exports Get-InvestigationAllowlistDisplay' {
        Get-Command Get-InvestigationAllowlistDisplay -Module InvestigationAllowlist | Should -Not -BeNullOrEmpty
    }

    It 'Exports Test-FileMatchesAllowlist' {
        Get-Command Test-FileMatchesAllowlist -Module InvestigationAllowlist | Should -Not -BeNullOrEmpty
    }
}
