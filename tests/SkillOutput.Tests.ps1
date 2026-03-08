BeforeAll {
    $repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
    Import-Module (Join-Path $repoRoot '.claude' 'skills' 'github' 'modules' 'SkillOutput.psm1') -Force
}

Describe 'Get-OutputFormat' {
    It 'returns JSON when requested explicitly' {
        Get-OutputFormat -Requested 'JSON' | Should -Be 'JSON'
    }

    It 'returns Human when requested explicitly' {
        Get-OutputFormat -Requested 'Human' | Should -Be 'Human'
    }

    It 'returns JSON when CI env var is set' {
        $env:CI = 'true'
        try {
            Get-OutputFormat -Requested 'Auto' | Should -Be 'JSON'
        }
        finally {
            Remove-Item Env:CI
        }
    }

    It 'returns JSON when GITHUB_ACTIONS env var is set' {
        $env:GITHUB_ACTIONS = 'true'
        try {
            Get-OutputFormat -Requested 'Auto' | Should -Be 'JSON'
        }
        finally {
            Remove-Item Env:GITHUB_ACTIONS
        }
    }
}

Describe 'Write-SkillOutput' {
    It 'produces valid JSON envelope in JSON mode' {
        $data = @{ Number = 42; Title = 'Test PR' }
        $json = Write-SkillOutput -Data $data -OutputFormat JSON -HumanSummary 'Test' -ScriptName 'Test.ps1'
        $envelope = $json | ConvertFrom-Json
        $envelope.Success | Should -BeTrue
        $envelope.Data.Number | Should -Be 42
        $envelope.Error | Should -BeNullOrEmpty
        $envelope.Metadata.Script | Should -Be 'Test.ps1'
        $envelope.Metadata.Timestamp | Should -Not -BeNullOrEmpty
    }

    It 'sets correct status values' {
        foreach ($status in @('PASS', 'FAIL', 'WARNING', 'INFO')) {
            $json = Write-SkillOutput -Data @{} -OutputFormat JSON -Status $status -ScriptName 'Test.ps1'
            $envelope = $json | ConvertFrom-Json
            $envelope.Success | Should -BeTrue
        }
    }

    It 'handles null data' {
        $json = Write-SkillOutput -Data $null -OutputFormat JSON -ScriptName 'Test.ps1'
        $envelope = $json | ConvertFrom-Json
        $envelope.Success | Should -BeTrue
        $envelope.Data | Should -BeNullOrEmpty
    }
}

Describe 'Write-SkillError' {
    It 'produces valid error envelope in JSON mode' {
        $json = Write-SkillError -Message 'Not found' -ExitCode 2 -ErrorType NotFound `
            -OutputFormat JSON -ScriptName 'Test.ps1'
        $envelope = $json | ConvertFrom-Json
        $envelope.Success | Should -BeFalse
        $envelope.Error.Message | Should -Be 'Not found'
        $envelope.Error.Code | Should -Be 2
        $envelope.Error.Type | Should -Be 'NotFound'
        $envelope.Metadata.Script | Should -Be 'Test.ps1'
    }

    It 'includes extra data when provided' {
        $json = Write-SkillError -Message 'API error' -ExitCode 3 -ErrorType ApiError `
            -OutputFormat JSON -ScriptName 'Test.ps1' -Extra @{ Number = 99 }
        $envelope = $json | ConvertFrom-Json
        $envelope.Success | Should -BeFalse
        $envelope.Data.Number | Should -Be 99
    }

    It 'validates error types' {
        $validTypes = @('NotFound', 'ApiError', 'AuthError', 'InvalidParams', 'Timeout', 'General')
        foreach ($type in $validTypes) {
            $json = Write-SkillError -Message 'test' -ExitCode 1 -ErrorType $type `
                -OutputFormat JSON -ScriptName 'Test.ps1'
            $envelope = $json | ConvertFrom-Json
            $envelope.Error.Type | Should -Be $type
        }
    }
}

Describe 'Validate-SkillOutput integration' {
    It 'validates a success envelope' {
        $json = Write-SkillOutput -Data @{ Result = 'ok' } -OutputFormat JSON -ScriptName 'Test.ps1'
        $result = $json | pwsh (Join-Path $PSScriptRoot '..' 'scripts' 'Validate-SkillOutput.ps1') 2>&1
        $LASTEXITCODE | Should -Be 0
    }

    It 'validates an error envelope' {
        $json = Write-SkillError -Message 'fail' -ExitCode 1 -ErrorType General `
            -OutputFormat JSON -ScriptName 'Test.ps1'
        $result = $json | pwsh (Join-Path $PSScriptRoot '..' 'scripts' 'Validate-SkillOutput.ps1') 2>&1
        $LASTEXITCODE | Should -Be 0
    }

    It 'rejects invalid JSON' {
        $result = 'not json' | pwsh (Join-Path $PSScriptRoot '..' 'scripts' 'Validate-SkillOutput.ps1') 2>&1
        $LASTEXITCODE | Should -Be 1
    }

    It 'rejects path traversal attempts' {
        $traversalPath = Join-Path $PSScriptRoot '..' '..' '..' 'etc' 'passwd'
        $result = pwsh (Join-Path $PSScriptRoot '..' 'scripts' 'Validate-SkillOutput.ps1') -InputFile $traversalPath 2>&1
        $LASTEXITCODE | Should -Be 1
        $result | Should -Match 'Path traversal attempt detected'
    }

    It 'rejects symlink traversal attempts' -Skip:($IsWindows) {
        $tempDir = Join-Path ([IO.Path]::GetTempPath()) "skilloutput-test-$(Get-Random)"
        $null = New-Item -ItemType Directory -Path $tempDir -Force
        $externalFile = Join-Path $tempDir 'external.json'
        '{"Success": true}' | Set-Content -Path $externalFile

        $repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
        $symlinkPath = Join-Path $repoRoot "test-symlink-$(Get-Random).json"
        try {
            $null = New-Item -ItemType SymbolicLink -Path $symlinkPath -Target $externalFile -ErrorAction Stop
            $result = pwsh (Join-Path $PSScriptRoot '..' 'scripts' 'Validate-SkillOutput.ps1') -InputFile $symlinkPath 2>&1
            $LASTEXITCODE | Should -Be 1
            $result | Should -Match 'Path traversal attempt detected'
        }
        finally {
            Remove-Item -Path $symlinkPath -Force -ErrorAction SilentlyContinue
            Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}
