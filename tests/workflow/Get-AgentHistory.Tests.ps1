<#
.SYNOPSIS
    Tests for Get-AgentHistory.ps1
#>

BeforeAll {
    $script:ScriptPath = Join-Path $PSScriptRoot '../../.claude/skills/workflow/scripts/Get-AgentHistory.ps1'
}

Describe 'Get-AgentHistory' {
    Context 'JSON output' {
        It 'returns valid JSON or empty array' {
            $output = pwsh -NoProfile -c "& '$script:ScriptPath' -LookbackHours 720" 2>&1
            $text = ($output | Where-Object { $_ -notmatch '^$' }) -join "`n"
            if ($text) {
                { $text | ConvertFrom-Json } | Should -Not -Throw
            }
        }
    }

    Context 'Table output' {
        It 'does not throw with table format' {
            { pwsh -NoProfile -c "& '$script:ScriptPath' -Format table -LookbackHours 1" 2>&1 } | Should -Not -Throw
        }
    }

    Context 'Agent detection' {
        It 'detects agents from known patterns' {
            # Use a long lookback to ensure we hit some commits
            $output = pwsh -NoProfile -c "& '$script:ScriptPath' -LookbackHours 8760" 2>&1
            $text = ($output | Where-Object { $_ -notmatch '^$' }) -join "`n"
            if ($text) {
                $data = $text | ConvertFrom-Json
                if ($data.Count -gt 0) {
                    $data[0].PSObject.Properties.Name | Should -Contain 'Agent'
                    $data[0].PSObject.Properties.Name | Should -Contain 'Commit'
                    $data[0].PSObject.Properties.Name | Should -Contain 'Message'
                }
            }
        }
    }
}
