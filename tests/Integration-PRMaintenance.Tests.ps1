BeforeAll {
    . "$PSScriptRoot/../scripts/Invoke-PRMaintenance.ps1"
    $script:Owner = 'rjmurillo'
    $script:Repo = 'ai-agents'

    # Discover which affected PRs are still open (avoid hardcoding)
    $script:AffectedBotPRs = @(365, 353, 301, 255, 235)
    $script:CopilotPR = 247
}

Describe 'Invoke-PRMaintenance Integration Tests' -Tag 'Integration' {
    BeforeEach {
        # Check if PRs are still open, skip if closed
        $openPRs = gh pr list --repo "$Owner/$Repo" --state open --json number 2>$null | ConvertFrom-Json
        $script:OpenPRNumbers = @($openPRs | ForEach-Object { $_.number })
    }

    It 'Bot-authored PRs with conflicts appear in ActionRequired (not Blocked)' -Skip:(-not ($OpenPRNumbers | Where-Object { $_ -in $AffectedBotPRs })) {
        # Run maintenance on affected PRs that are still open
        $prsToTest = @($AffectedBotPRs | Where-Object { $_ -in $OpenPRNumbers })
        if (-not $prsToTest -or $prsToTest.Count -eq 0) {
            Set-ItResult -Skipped -Because "No affected bot PRs are currently open"
            return
        }

        $results = Invoke-PRMaintenance -Owner $Owner -Repo $Repo -DryRun

        foreach ($prNum in $prsToTest) {
            $inActionRequired = $results.ActionRequired | Where-Object { $_.PR -eq $prNum }
            $inBlocked = $results.Blocked | Where-Object { $_.PR -eq $prNum }

            $inActionRequired | Should -Not -BeNullOrEmpty -Because "PR #$prNum should be in ActionRequired"
            $inBlocked | Should -BeNullOrEmpty -Because "PR #$prNum should NOT be in Blocked"
        }
    }

    It 'PR #247 (copilot PR) triggers synthesis workflow' -Skip:($CopilotPR -notin $OpenPRNumbers) {
        $results = Invoke-PRMaintenance -Owner $Owner -Repo $Repo -DryRun

        $copilotEntry = $results.ActionRequired | Where-Object { $_.PR -eq $CopilotPR }
        $copilotEntry.Reason | Should -Be 'COPILOT_SYNTHESIS_NEEDED'
    }

    It 'No PR appears in both ActionRequired and Blocked' {
        $results = Invoke-PRMaintenance -Owner $Owner -Repo $Repo -DryRun

        foreach ($actionItem in $results.ActionRequired) {
            $duplicate = $results.Blocked | Where-Object { $_.PR -eq $actionItem.PR }
            $duplicate | Should -BeNullOrEmpty -Because "PR #$($actionItem.PR) should not be in both lists"
        }
    }
}
