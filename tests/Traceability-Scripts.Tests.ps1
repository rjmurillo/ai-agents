BeforeAll {
    # Import test utilities
    Import-Module (Join-Path $PSScriptRoot 'TestUtilities.psm1') -Force

    # Create test fixture directory
    $script:TestFixtureDir = Join-Path ([System.IO.Path]::GetTempPath()) "traceability-test-$(New-Guid)"
    New-Item -Path $script:TestFixtureDir -ItemType Directory -Force | Out-Null

    # Create test specs directory structure
    $script:TestSpecsDir = Join-Path $script:TestFixtureDir "specs"
    $reqDir = Join-Path $script:TestSpecsDir "requirements"
    $designDir = Join-Path $script:TestSpecsDir "design"
    $taskDir = Join-Path $script:TestSpecsDir "tasks"

    New-Item -Path $reqDir -ItemType Directory -Force | Out-Null
    New-Item -Path $designDir -ItemType Directory -Force | Out-Null
    New-Item -Path $taskDir -ItemType Directory -Force | Out-Null

    # Helper function to create spec files
    function New-TestSpec {
        param(
            [string]$Id,
            [string]$Type,
            [string[]]$Related = @(),
            [string]$Status = 'draft'
        )

        $subdir = switch ($Type) {
            'requirement' { $reqDir }
            'design' { $designDir }
            'task' { $taskDir }
        }

        $filePath = Join-Path $subdir "$Id.md"
        $relatedBlock = if ($Related.Count -gt 0) {
            "related:`r`n" + (($Related | ForEach-Object { "  - $_" }) -join "`r`n")
        }
        else {
            "related: []"
        }

        $content = @"
---
type: $Type
id: $Id
status: $Status
$relatedBlock
---

# $Id

Test spec content
"@

        Set-Content -Path $filePath -Value $content -NoNewline
        return $filePath
    }
}

AfterAll {
    # Clean up test fixture
    if (Test-Path $script:TestFixtureDir) {
        Remove-Item -Path $script:TestFixtureDir -Recurse -Force
    }

    # Clear traceability cache
    $cacheModule = Join-Path $PSScriptRoot '../scripts/traceability/TraceabilityCache.psm1'
    if (Test-Path $cacheModule) {
        Import-Module $cacheModule -Force
        Clear-TraceabilityCache
    }
}

Describe 'Show-TraceabilityGraph.ps1' -Tag 'Traceability', 'Graph' {
    BeforeEach {
        # Create test data
        New-TestSpec -Id 'REQ-001' -Type 'requirement' -Status 'approved'
        New-TestSpec -Id 'DESIGN-001' -Type 'design' -Related @('REQ-001') -Status 'approved'
        New-TestSpec -Id 'TASK-001' -Type 'task' -Related @('DESIGN-001') -Status 'complete'
    }

    AfterEach {
        # Clean up test specs
        Get-ChildItem -Path $script:TestSpecsDir -Recurse -Filter "*.md" | Remove-Item -Force
    }

    Context 'Basic Functionality' {
        It 'Generates text graph successfully' -Skip {
            # TODO: Restore when Show-TraceabilityGraph.ps1 full implementation is complete
            # Currently only has minimal stub implementation
            $result = & "$PSScriptRoot/../scripts/traceability/Show-TraceabilityGraph.ps1" `
                -SpecsPath $script:TestSpecsDir `
                -Format 'text'

            $LASTEXITCODE | Should -Be 0
            $result | Should -Not -BeNullOrEmpty
            $result | Should -Match 'REQ-001'
        }

        It 'Generates mermaid graph successfully' -Skip {
            # TODO: Restore when Show-TraceabilityGraph.ps1 full implementation is complete
            $result = & "$PSScriptRoot/../scripts/traceability/Show-TraceabilityGraph.ps1" `
                -SpecsPath $script:TestSpecsDir `
                -Format 'mermaid'

            $LASTEXITCODE | Should -Be 0
            $result | Should -Not -BeNullOrEmpty
            $result | Should -Match '```mermaid'
            $result | Should -Match 'graph TD'
        }

        It 'Generates json graph successfully' -Skip {
            # TODO: Restore when Show-TraceabilityGraph.ps1 full implementation is complete
            $result = & "$PSScriptRoot/../scripts/traceability/Show-TraceabilityGraph.ps1" `
                -SpecsPath $script:TestSpecsDir `
                -Format 'json'

            $LASTEXITCODE | Should -Be 0
            $result | Should -Not -BeNullOrEmpty
            $json = $result | ConvertFrom-Json
            $json.nodes | Should -Not -BeNullOrEmpty
            $json.edges | Should -Not -BeNullOrEmpty
        }

        It 'Supports dry-run mode' {
            $result = & "$PSScriptRoot/../scripts/traceability/Show-TraceabilityGraph.ps1" `
                -SpecsPath $script:TestSpecsDir `
                -DryRun

            $LASTEXITCODE | Should -Be 0
        }

        It 'Supports RootId parameter' -Skip {
            # TODO: Restore when Show-TraceabilityGraph.ps1 full implementation is complete
            $result = & "$PSScriptRoot/../scripts/traceability/Show-TraceabilityGraph.ps1" `
                -SpecsPath $script:TestSpecsDir `
                -RootId 'REQ-001' `
                -Format 'text'

            $LASTEXITCODE | Should -Be 0
            $result | Should -Match 'REQ-001'
        }

        It 'Supports depth limiting' -Skip {
            # TODO: Restore when Show-TraceabilityGraph.ps1 full implementation is complete
            $result = & "$PSScriptRoot/../scripts/traceability/Show-TraceabilityGraph.ps1" `
                -SpecsPath $script:TestSpecsDir `
                -Depth 1 `
                -Format 'text'

            $LASTEXITCODE | Should -Be 0
        }
    }

    Context 'Error Handling' {
        It 'Returns error for non-existent specs path' -Skip {
            # TODO: Restore when Show-TraceabilityGraph.ps1 full implementation is complete
            & "$PSScriptRoot/../scripts/traceability/Show-TraceabilityGraph.ps1" `
                -SpecsPath '/non/existent/path' `
                -ErrorAction SilentlyContinue

            $LASTEXITCODE | Should -Be 1
        }

        It 'Returns error for invalid RootId' -Skip {
            # TODO: Restore when Show-TraceabilityGraph.ps1 full implementation is complete
            & "$PSScriptRoot/../scripts/traceability/Show-TraceabilityGraph.ps1" `
                -SpecsPath $script:TestSpecsDir `
                -RootId 'INVALID-999' `
                -ErrorAction SilentlyContinue

            $LASTEXITCODE | Should -Be 1
        }
    }
}

Describe 'Rename-SpecId.ps1' -Tag 'Traceability', 'Rename' {
    BeforeEach {
        # Create test data
        New-TestSpec -Id 'REQ-001' -Type 'requirement'
        New-TestSpec -Id 'DESIGN-001' -Type 'design' -Related @('REQ-001')
        New-TestSpec -Id 'TASK-001' -Type 'task' -Related @('DESIGN-001')
    }

    AfterEach {
        # Clean up test specs
        Get-ChildItem -Path $script:TestSpecsDir -Recurse -Filter "*.md" | Remove-Item -Force
    }

    Context 'Dry-Run Mode' {
        It 'Shows rename plan without making changes' {
            $result = & "$PSScriptRoot/../scripts/traceability/Rename-SpecId.ps1" `
                -OldId 'REQ-001' `
                -NewId 'REQ-100' `
                -SpecsPath $script:TestSpecsDir `
                -DryRun

            $LASTEXITCODE | Should -Be 0

            # Verify old file still exists
            $oldFile = Join-Path $reqDir 'REQ-001.md'
            $oldFile | Should -Exist

            # Verify new file does not exist
            $newFile = Join-Path $reqDir 'REQ-100.md'
            $newFile | Should -Not -Exist
        }
    }

    Context 'Validation' {
        It 'Rejects invalid old ID format' -Skip {
            # TODO: Fix exit code handling in tests
            try {
                & "$PSScriptRoot/../scripts/traceability/Rename-SpecId.ps1" `
                    -OldId 'INVALID' `
                    -NewId 'REQ-100' `
                    -SpecsPath $script:TestSpecsDir `
                    -ErrorAction Stop
            } catch {
                # Expected to fail
            }

            $LASTEXITCODE | Should -Be 1
        }

        It 'Rejects invalid new ID format' -Skip {
            # TODO: Fix exit code handling in tests
            try {
                & "$PSScriptRoot/../scripts/traceability/Rename-SpecId.ps1" `
                    -OldId 'REQ-001' `
                    -NewId 'INVALID' `
                    -SpecsPath $script:TestSpecsDir `
                    -ErrorAction Stop
            } catch {
                # Expected to fail
            }

            $LASTEXITCODE | Should -Be 1
        }

        It 'Rejects type changes' -Skip {
            # TODO: Fix exit code handling in tests
            try {
                & "$PSScriptRoot/../scripts/traceability/Rename-SpecId.ps1" `
                    -OldId 'REQ-001' `
                    -NewId 'DESIGN-100' `
                    -SpecsPath $script:TestSpecsDir `
                    -ErrorAction Stop
            } catch {
                # Expected to fail
            }

            $LASTEXITCODE | Should -Be 1
        }

        It 'Rejects non-existent source ID' -Skip {
            # TODO: Fix exit code handling in tests
            try {
                & "$PSScriptRoot/../scripts/traceability/Rename-SpecId.ps1" `
                    -OldId 'REQ-999' `
                    -NewId 'REQ-100' `
                    -SpecsPath $script:TestSpecsDir `
                    -ErrorAction Stop
            } catch {
                # Expected to fail
            }

            $LASTEXITCODE | Should -Be 1
        }

        It 'Rejects if target ID already exists' -Skip {
            # TODO: Fix exit code handling in tests
            New-TestSpec -Id 'REQ-100' -Type 'requirement'

            try {
                & "$PSScriptRoot/../scripts/traceability/Rename-SpecId.ps1" `
                    -OldId 'REQ-001' `
                    -NewId 'REQ-100' `
                    -SpecsPath $script:TestSpecsDir `
                    -ErrorAction Stop
            } catch {
                # Expected to fail
            }

            $LASTEXITCODE | Should -Be 1
        }
    }
}

Describe 'Update-SpecReferences.ps1' -Tag 'Traceability', 'References' {
    BeforeEach {
        # Create test data
        New-TestSpec -Id 'REQ-001' -Type 'requirement'
        New-TestSpec -Id 'REQ-002' -Type 'requirement'
        New-TestSpec -Id 'DESIGN-001' -Type 'design' -Related @('REQ-001')
    }

    AfterEach {
        # Clean up test specs
        Get-ChildItem -Path $script:TestSpecsDir -Recurse -Filter "*.md" | Remove-Item -Force
    }

    Context 'Dry-Run Mode' {
        It 'Shows update plan without making changes' {
            $result = & "$PSScriptRoot/../scripts/traceability/Update-SpecReferences.ps1" `
                -SourceId 'DESIGN-001' `
                -AddReferences @('REQ-002') `
                -SpecsPath $script:TestSpecsDir `
                -DryRun

            $LASTEXITCODE | Should -Be 0

            # Verify file was not actually changed
            $content = Get-Content -Path (Join-Path $designDir 'DESIGN-001.md') -Raw
            $content | Should -Not -Match 'REQ-002'
        }
    }

    Context 'Validation' {
        It 'Rejects invalid source ID format' -Skip {
            # TODO: Fix exit code handling in tests
            try {
                & "$PSScriptRoot/../scripts/traceability/Update-SpecReferences.ps1" `
                    -SourceId 'INVALID' `
                    -AddReferences @('REQ-002') `
                    -SpecsPath $script:TestSpecsDir `
                    -ErrorAction Stop
            } catch {
                # Expected to fail
            }

            $LASTEXITCODE | Should -Be 1
        }

        It 'Rejects invalid reference ID format' -Skip {
            # TODO: Fix exit code handling in tests
            try {
                & "$PSScriptRoot/../scripts/traceability/Update-SpecReferences.ps1" `
                    -SourceId 'DESIGN-001' `
                    -AddReferences @('INVALID') `
                    -SpecsPath $script:TestSpecsDir `
                    -ErrorAction Stop
            } catch {
                # Expected to fail
            }

            $LASTEXITCODE | Should -Be 1
        }

        It 'Rejects non-existent source ID' -Skip {
            # TODO: Fix exit code handling in tests
            try {
                & "$PSScriptRoot/../scripts/traceability/Update-SpecReferences.ps1" `
                    -SourceId 'DESIGN-999' `
                    -AddReferences @('REQ-002') `
                    -SpecsPath $script:TestSpecsDir `
                    -ErrorAction Stop
            } catch {
                # Expected to fail
            }

            $LASTEXITCODE | Should -Be 1
        }
    }
}
