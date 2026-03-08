<#
.SYNOPSIS
    Tests for Sync-SessionDocumentation.ps1
#>

BeforeAll {
    $script:ScriptPath = Join-Path $PSScriptRoot '../../.claude/skills/workflow/scripts/Sync-SessionDocumentation.ps1'
}

Describe 'Sync-SessionDocumentation' {
    Context 'DryRun mode' {
        It 'produces output without writing files' {
            $output = pwsh -NoProfile -c "& '$script:ScriptPath' -DryRun" 2>&1
            $text = $output -join "`n"
            $text | Should -Match 'DRY RUN'
            $text | Should -Match 'Structured Output'
        }

        It 'emits valid JSON in structured output' {
            $output = pwsh -NoProfile -c "& '$script:ScriptPath' -DryRun" 2>&1
            $jsonStart = $false
            $jsonLines = @()
            foreach ($line in $output) {
                if ($line -match 'Structured Output') { $jsonStart = $true; continue }
                if ($jsonStart) { $jsonLines += $line }
            }
            $json = $jsonLines -join "`n"
            { $json | ConvertFrom-Json } | Should -Not -Throw
        }

        It 'JSON contains required fields' {
            $output = pwsh -NoProfile -c "& '$script:ScriptPath' -DryRun" 2>&1
            $jsonStart = $false
            $jsonLines = @()
            foreach ($line in $output) {
                if ($line -match 'Structured Output') { $jsonStart = $true; continue }
                if ($jsonStart) { $jsonLines += $line }
            }
            $obj = ($jsonLines -join "`n") | ConvertFrom-Json
            $obj.PSObject.Properties.Name | Should -Contain 'date'
            $obj.PSObject.Properties.Name | Should -Contain 'branch'
            $obj.PSObject.Properties.Name | Should -Contain 'commits'
            $obj.PSObject.Properties.Name | Should -Contain 'agents'
            $obj.PSObject.Properties.Name | Should -Contain 'learnings'
        }
    }

    Context 'Report content' {
        It 'generates Mermaid diagram in report' {
            $output = pwsh -NoProfile -c "& '$script:ScriptPath' -DryRun" 2>&1
            $text = $output -join "`n"
            $text | Should -Match 'mermaid'
            $text | Should -Match 'sequenceDiagram'
        }

        It 'includes workflow sections' {
            $output = pwsh -NoProfile -c "& '$script:ScriptPath' -DryRun" 2>&1
            $text = $output -join "`n"
            $text | Should -Match 'Agents Invoked'
            $text | Should -Match 'Decisions Made'
            $text | Should -Match 'Artifacts Created'
            $text | Should -Match 'Retrospective Learnings'
        }
    }

    Context 'LookbackHours parameter' {
        It 'accepts custom lookback' {
            $output = pwsh -NoProfile -c "& '$script:ScriptPath' -DryRun -LookbackHours 1" 2>&1
            $text = $output -join "`n"
            $text | Should -Match 'Lookback: 1 hours'
        }
    }

    Context 'Security: path traversal prevention (CWE-22)' {
        It 'throws when OutputPath is outside repository root' {
            $traversalPath = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), 'pwned.md')
            $result = pwsh -NoProfile -c "
                try {
                    & '$script:ScriptPath' -OutputPath '$traversalPath'
                    exit 0
                } catch {
                    Write-Output 'TRAVERSAL_BLOCKED'
                    exit 1
                }
            " 2>&1
            $text = $result -join "`n"
            $text | Should -Match 'TRAVERSAL_BLOCKED|Path traversal attempt detected|outside the repository root'
        }
    }
}
