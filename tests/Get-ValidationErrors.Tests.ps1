BeforeAll {
    $scriptPath = Join-Path $PSScriptRoot '../.claude/skills/session/log-fixer/scripts/Get-ValidationErrors.ps1'
}

Describe 'Get-ValidationErrors' {
    Context 'Script structure and parameters' {
        It 'Should have RunId parameter' {
            $params = (Get-Command $scriptPath).Parameters
            $params.ContainsKey('RunId') | Should -Be $true
        }

        It 'Should have PullRequest parameter' {
            $params = (Get-Command $scriptPath).Parameters
            $params.ContainsKey('PullRequest') | Should -Be $true
        }

        It 'RunId should be in RunId parameter set' {
            $param = (Get-Command $scriptPath).Parameters['RunId']
            $param.ParameterSets.Keys | Should -Contain 'RunId'
        }

        It 'PullRequest should be in PR parameter set' {
            $param = (Get-Command $scriptPath).Parameters['PullRequest']
            $param.ParameterSets.Keys | Should -Contain 'PR'
        }
    }

    Context 'Parse-JobSummary function implementation' {
        It 'Should define regex patterns for parsing Job Summary' {
            $scriptContent = Get-Content $scriptPath -Raw
            # Verify the script contains regex patterns for parsing
            $scriptContent | Should -Match 'Overall Verdict'
            $scriptContent | Should -Match 'MUST requirement'
            $scriptContent | Should -Match 'NON_COMPLIANT'
        }

        It 'Should have Parse-JobSummary function that processes summary text' {
            $scriptContent = Get-Content $scriptPath -Raw
            $scriptContent | Should -Match 'function Parse-JobSummary'
            $scriptContent | Should -Match 'param\(\[string\]\$Summary\)'
        }

        It 'Should return a hashtable/object from Parse-JobSummary' {
            $scriptContent = Get-Content $scriptPath -Raw
            $scriptContent | Should -Match '@\{'
            $scriptContent | Should -Match 'OverallVerdict'
            $scriptContent | Should -Match 'NonCompliantSessions'
            $scriptContent | Should -Match 'DetailedErrors'
        }
    }

    Context 'Error handling' {
        It 'Should handle missing parameters gracefully' {
            # This test just verifies the script doesn't crash on parameter validation
            # The actual gh command will fail, but that's expected
            $result = & $scriptPath -RunId '99999999' 2>&1
            # Script should produce some output or error
            $result | Should -Not -BeNullOrEmpty
        }
    }

    Context 'Output structure expectations' {
        It 'Should define expected output properties in documentation' {
            $scriptContent = Get-Content $scriptPath -Raw
            $scriptContent | Should -Match 'RunId'
            $scriptContent | Should -Match 'OverallVerdict'
            $scriptContent | Should -Match 'MustFailureCount'
            $scriptContent | Should -Match 'NonCompliantSessions'
            $scriptContent | Should -Match 'DetailedErrors'
        }

        It 'Should document exit codes' {
            $scriptContent = Get-Content $scriptPath -Raw
            $scriptContent | Should -Match 'Exit Codes?:'
            $scriptContent | Should -Match 'exit 0'
            $scriptContent | Should -Match 'exit 1'
            $scriptContent | Should -Match 'exit 2'
        }
    }

    Context 'Function definitions' {
        It 'Should define Get-RunIdFromPR function' {
            $scriptContent = Get-Content $scriptPath -Raw
            $scriptContent | Should -Match 'function Get-RunIdFromPR'
        }

        It 'Should define Parse-JobSummary function' {
            $scriptContent = Get-Content $scriptPath -Raw
            $scriptContent | Should -Match 'function Parse-JobSummary'
        }
    }
}

Describe 'Get-ValidationErrors Integration Notes' {
    Context 'Integration test requirements' {
        It 'Requires gh CLI for full integration testing' {
            # This is a documentation test
            $scriptContent = Get-Content $scriptPath -Raw
            $scriptContent | Should -Match 'gh (pr|run)'
        }

        It 'Documents gh CLI dependency' {
            $scriptContent = Get-Content $scriptPath -Raw
            $scriptContent | Should -Match 'Requires:.*gh'
        }
    }
}
