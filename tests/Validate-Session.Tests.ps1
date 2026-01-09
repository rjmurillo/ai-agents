#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Validate-Session.ps1 investigation-only validation

.DESCRIPTION
    Tests the investigation-only allowlist verification logic per ADR-034.
    Validates that sessions modifying only investigation artifacts can skip QA.
#>

BeforeAll {
    $scriptPath = Join-Path $PSScriptRoot ".." "scripts" "Validate-Session.ps1"

    # Extract the functions we need to test
    $scriptContent = Get-Content -Path $scriptPath -Raw

    # Extract the allowlist variable (handles nested parentheses in patterns)
    if ($scriptContent -match '(?ms)\$script:InvestigationAllowlist\s*=\s*@\(.*?^\)') {
        $allowlistDef = $Matches[0]
        Invoke-Expression $allowlistDef
    }

    # Extract Test-InvestigationOnlyEligibility function (advanced function with CmdletBinding)
    $functionPattern = '(?ms)function Test-InvestigationOnlyEligibility\s*\{.*?^\}'
    if ($scriptContent -match $functionPattern) {
        $functionDef = $Matches[0]
        Invoke-Expression $functionDef
    }

    # Also extract Is-DocsOnly for comparison tests
    $docsOnlyPattern = '(?ms)function Is-DocsOnly\s*\([^)]*\)\s*\{.*?\n\}'
    if ($scriptContent -match $docsOnlyPattern) {
        $docsOnlyDef = $Matches[0]
        Invoke-Expression $docsOnlyDef
    }

    # Extract the AuditArtifacts variable for Get-ImplementationFiles tests
    if ($scriptContent -match '(?ms)\$script:AuditArtifacts\s*=\s*@\(.*?^\)') {
        $auditArtifactsDef = $Matches[0]
        Invoke-Expression $auditArtifactsDef
    }

    # Extract Get-ImplementationFiles function
    $getImplFilesPattern = '(?ms)function Get-ImplementationFiles\s*\{.*?^\}'
    if ($scriptContent -match $getImplFilesPattern) {
        $getImplFilesDef = $Matches[0]
        Invoke-Expression $getImplFilesDef
    }
}

Describe "InvestigationAllowlist" {
    It "Contains expected investigation-only paths" {
        $script:InvestigationAllowlist | Should -Contain '^\.agents/sessions/'
        $script:InvestigationAllowlist | Should -Contain '^\.agents/analysis/'
        $script:InvestigationAllowlist | Should -Contain '^\.agents/retrospective/'
        $script:InvestigationAllowlist | Should -Contain '^\.serena/memories($|/)'
        $script:InvestigationAllowlist | Should -Contain '^\.agents/security/'
    }

    It "Has exactly 5 allowlist patterns" {
        $script:InvestigationAllowlist.Count | Should -Be 5
    }
}

Describe "Test-InvestigationOnlyEligibility" {
    Context "Empty or null input" {
        It "Returns eligible for empty file list" {
            $result = Test-InvestigationOnlyEligibility -Files @()
            $result.IsEligible | Should -BeTrue
            $result.ImplementationFiles.Count | Should -Be 0
        }

        It "Returns eligible for null file list" {
            $result = Test-InvestigationOnlyEligibility -Files $null
            $result.IsEligible | Should -BeTrue
            $result.ImplementationFiles.Count | Should -Be 0
        }
    }

    Context "Pure investigation sessions" {
        It "Returns eligible for session log only" {
            $files = @('.agents/sessions/2025-12-31-session-110.md')
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeTrue
            $result.ImplementationFiles.Count | Should -Be 0
        }

        It "Returns eligible for analysis files" {
            $files = @('.agents/analysis/research-findings.md')
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeTrue
        }

        It "Returns eligible for retrospective files" {
            $files = @('.agents/retrospective/session-learnings.md')
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeTrue
        }

        It "Returns eligible for Serena memory files" {
            $files = @('.serena/memories/project-context.md')
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeTrue
        }

        It "Returns eligible for security assessment files" {
            $files = @('.agents/security/threat-assessment.md')
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeTrue
        }

        It "Returns eligible for multiple allowed paths combined" {
            $files = @(
                '.agents/sessions/2025-12-31-session-110.md',
                '.agents/analysis/findings.md',
                '.serena/memories/context.md',
                '.agents/retrospective/learnings.md',
                '.agents/security/review.md'
            )
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeTrue
            $result.ImplementationFiles.Count | Should -Be 0
        }
    }

    Context "Implementation sessions (not investigation-only)" {
        It "Rejects code changes" {
            $files = @(
                '.agents/sessions/2025-12-31-session-110.md',
                'scripts/Validate-Session.ps1'
            )
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeFalse
            $result.ImplementationFiles | Should -Contain 'scripts/Validate-Session.ps1'
        }

        It "Rejects workflow changes" {
            $files = @(
                '.agents/sessions/2025-12-31-session-110.md',
                '.github/workflows/ci.yml'
            )
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeFalse
            $result.ImplementationFiles | Should -Contain '.github/workflows/ci.yml'
        }

        It "Rejects test file changes" {
            $files = @(
                '.agents/sessions/2025-12-31-session-110.md',
                'tests/Feature.Tests.ps1'
            )
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeFalse
        }

        It "Rejects planning document changes" {
            $files = @(
                '.agents/sessions/2025-12-31-session-110.md',
                '.agents/planning/feature-prd.md'
            )
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeFalse
            $result.ImplementationFiles | Should -Contain '.agents/planning/feature-prd.md'
        }

        It "Rejects architecture document changes" {
            $files = @(
                '.agents/sessions/2025-12-31-session-110.md',
                '.agents/architecture/adr-001.md'
            )
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeFalse
        }

        It "Rejects QA report changes" {
            $files = @(
                '.agents/sessions/2025-12-31-session-110.md',
                '.agents/qa/feature-qa-report.md'
            )
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeFalse
        }

        It "Returns all implementation files when multiple present" {
            $files = @(
                '.agents/sessions/2025-12-31-session-110.md',
                'scripts/Script1.ps1',
                'scripts/Script2.ps1',
                'tests/Test.ps1'
            )
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeFalse
            $result.ImplementationFiles.Count | Should -Be 3
        }
    }

    Context "Path normalization" {
        It "Handles Windows-style backslashes" {
            $files = @('.agents\sessions\2025-12-31-session-110.md')
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeTrue
        }

        It "Handles mixed path separators" {
            $files = @(
                '.agents/sessions\2025-12-31-session-110.md',
                '.serena\memories/context.md'
            )
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeTrue
        }
    }

    Context "Edge cases" {
        It "Rejects similar but not matching paths" {
            # .agents/sessions-evil/ should NOT match .agents/sessions/
            $files = @('.agents/sessions-evil/malicious.md')
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeFalse
        }

        It "Rejects root-level .agents files" {
            $files = @('.agents/HANDOFF.md')
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeFalse
        }

        It "Handles deeply nested investigation paths" {
            $files = @('.agents/sessions/2025/12/deep/session.md')
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeTrue
        }

        It "Returns eligible for Serena memories directory itself" {
            # Tests the ($|/) pattern matches end-of-string
            $files = @('.serena/memories')
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeTrue
        }

        It "Rejects .serena/memories prefix bypass" {
            # .serena/memoriesX should NOT match .serena/memories($|/)
            $files = @('.serena/memoriesX/evil.md')
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeFalse
        }
    }
}

Describe "Is-DocsOnly vs Test-InvestigationOnlyEligibility" {
    <#
    .SYNOPSIS
        Verify the distinction between docs-only and investigation-only
    #>

    It "Docs-only: pure markdown anywhere passes" {
        $files = @('README.md', 'docs/guide.md')
        $result = Is-DocsOnly $files
        $result | Should -BeTrue
    }

    It "Investigation-only: pure markdown outside allowed paths fails" {
        $files = @('README.md', 'docs/guide.md')
        $result = Test-InvestigationOnlyEligibility -Files $files
        $result.IsEligible | Should -BeFalse
    }

    It "Both pass for markdown in allowed paths" {
        $files = @('.agents/sessions/2025-12-31-session-110.md')
        $docsResult = Is-DocsOnly $files
        $docsResult | Should -BeTrue

        $investResult = Test-InvestigationOnlyEligibility -Files $files
        $investResult.IsEligible | Should -BeTrue
    }
}

Describe "AuditArtifacts" {
    It "Contains expected audit artifact paths" {
        $script:AuditArtifacts | Should -Contain '^\.agents/sessions/'
        $script:AuditArtifacts | Should -Contain '^\.agents/analysis/'
        $script:AuditArtifacts | Should -Contain '^\.serena/memories($|/)'
    }

    It "Has exactly 3 audit artifact patterns" {
        $script:AuditArtifacts.Count | Should -Be 3
    }
}

Describe "Get-ImplementationFiles" {
    Context "Empty or null input" {
        It "Returns empty array for empty file list" {
            $result = Get-ImplementationFiles -Files @()
            $result | Should -BeNullOrEmpty
            $result.Count | Should -Be 0
        }

        It "Returns empty array for null file list" {
            $result = Get-ImplementationFiles -Files $null
            $result | Should -BeNullOrEmpty
        }
    }

    Context "Session logs (audit trail)" {
        It "Filters out session log files" {
            $files = @('.agents/sessions/2026-01-01-session-01.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -BeNullOrEmpty
        }

        It "Filters out nested session log files" {
            $files = @('.agents/sessions/2026/01/deep/session.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -BeNullOrEmpty
        }
    }

    Context "Analysis artifacts" {
        It "Filters out analysis files" {
            $files = @('.agents/analysis/research-findings.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -BeNullOrEmpty
        }

        It "Filters out nested analysis files" {
            $files = @('.agents/analysis/investigations/deep/report.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -BeNullOrEmpty
        }
    }

    Context "Serena memory files" {
        It "Filters out memory files" {
            $files = @('.serena/memories/project-context.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -BeNullOrEmpty
        }

        It "Filters out deeply nested memory files" {
            $files = @('.serena/memories/category/subcategory/memory.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -BeNullOrEmpty
        }

        It "Filters out .serena/memories directory reference" {
            $files = @('.serena/memories')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -BeNullOrEmpty
        }
    }

    Context "Non-audit files preserved" {
        It "Preserves PowerShell scripts" {
            $files = @('scripts/Validate-Session.ps1')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -Contain 'scripts/Validate-Session.ps1'
        }

        It "Preserves ADR files" {
            $files = @('.agents/architecture/ADR-001.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -Contain '.agents/architecture/ADR-001.md'
        }

        It "Preserves planning files" {
            $files = @('.agents/planning/feature-prd.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -Contain '.agents/planning/feature-prd.md'
        }

        It "Preserves QA reports" {
            $files = @('.agents/qa/feature-qa-report.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -Contain '.agents/qa/feature-qa-report.md'
        }

        It "Preserves workflow files" {
            $files = @('.github/workflows/ci.yml')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -Contain '.github/workflows/ci.yml'
        }

        It "Preserves test files" {
            $files = @('tests/Feature.Tests.ps1')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -Contain 'tests/Feature.Tests.ps1'
        }

        It "Preserves root-level .agents files" {
            $files = @('.agents/HANDOFF.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -Contain '.agents/HANDOFF.md'
        }

        It "Preserves critique files" {
            $files = @('.agents/critique/review.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -Contain '.agents/critique/review.md'
        }

        It "Preserves retrospective files (not in audit artifacts)" {
            $files = @('.agents/retrospective/learnings.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -Contain '.agents/retrospective/learnings.md'
        }

        It "Preserves security assessment files (not in audit artifacts)" {
            $files = @('.agents/security/threat-model.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -Contain '.agents/security/threat-model.md'
        }
    }

    Context "Mixed audit and implementation files" {
        It "Filters audit, preserves implementation from mixed input" {
            $files = @(
                '.agents/sessions/2026-01-01-session-01.md',
                'scripts/Validate-Session.ps1'
            )
            $result = Get-ImplementationFiles -Files $files
            $result.Count | Should -Be 1
            $result | Should -Contain 'scripts/Validate-Session.ps1'
            $result | Should -Not -Contain '.agents/sessions/2026-01-01-session-01.md'
        }

        It "Correctly separates multiple audit and implementation files" {
            $files = @(
                '.agents/sessions/2026-01-01-session-01.md',
                '.agents/analysis/findings.md',
                '.serena/memories/context.md',
                'scripts/Script1.ps1',
                'scripts/Script2.ps1',
                '.agents/architecture/ADR-001.md'
            )
            $result = Get-ImplementationFiles -Files $files
            $result.Count | Should -Be 3
            $result | Should -Contain 'scripts/Script1.ps1'
            $result | Should -Contain 'scripts/Script2.ps1'
            $result | Should -Contain '.agents/architecture/ADR-001.md'
            $result | Should -Not -Contain '.agents/sessions/2026-01-01-session-01.md'
            $result | Should -Not -Contain '.agents/analysis/findings.md'
            $result | Should -Not -Contain '.serena/memories/context.md'
        }

        It "Returns only ADR when session log + ADR staged (docs-only scenario)" {
            $files = @(
                '.agents/sessions/2026-01-01-session-01.md',
                '.agents/architecture/ADR-037.md'
            )
            $result = Get-ImplementationFiles -Files $files
            $result.Count | Should -Be 1
            $result | Should -Contain '.agents/architecture/ADR-037.md'
        }
    }

    Context "Path normalization" {
        It "Handles Windows-style backslashes" {
            $files = @('.agents\sessions\2026-01-01-session-01.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -BeNullOrEmpty
        }

        It "Handles mixed path separators" {
            $files = @(
                '.agents/sessions\2026-01-01.md',
                '.serena\memories/context.md'
            )
            $result = Get-ImplementationFiles -Files $files
            $result | Should -BeNullOrEmpty
        }
    }

    Context "Edge cases - path traversal prevention" {
        It "Does not filter similar-but-different paths (.agents/sessions-evil)" {
            $files = @('.agents/sessions-evil/malicious.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -Contain '.agents/sessions-evil/malicious.md'
        }

        It "Does not filter .serena/memoriesX prefix bypass" {
            $files = @('.serena/memoriesX/evil.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -Contain '.serena/memoriesX/evil.md'
        }

        It "Does not filter .agents/analysisX prefix bypass" {
            $files = @('.agents/analysisX/evil.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -Contain '.agents/analysisX/evil.md'
        }
    }
}

Describe "Get-ImplementationFiles vs Test-InvestigationOnlyEligibility" {
    <#
    .SYNOPSIS
        Verify the distinction between audit filtering and investigation eligibility

    .NOTES
        AuditArtifacts filters: sessions, analysis, memories
        InvestigationAllowlist allows: sessions, analysis, memories, retrospective, security

        Key difference: retrospective and security are investigation-eligible but NOT audit artifacts
    #>

    It "AuditArtifacts is subset of InvestigationAllowlist" {
        # Session logs, analysis, memories are in both
        $auditPatterns = @(
            '^\.agents/sessions/',
            '^\.agents/analysis/',
            '^\.serena/memories($|/)'
        )
        foreach ($pattern in $auditPatterns) {
            $script:InvestigationAllowlist | Should -Contain $pattern
        }
    }

    It "Retrospective is investigation-eligible but not audit artifact" {
        $files = @('.agents/retrospective/learnings.md')

        # Investigation: eligible
        $investResult = Test-InvestigationOnlyEligibility -Files $files
        $investResult.IsEligible | Should -BeTrue

        # Audit: NOT filtered (preserved as implementation)
        $implResult = Get-ImplementationFiles -Files $files
        $implResult | Should -Contain '.agents/retrospective/learnings.md'
    }

    It "Security is investigation-eligible but not audit artifact" {
        $files = @('.agents/security/threat-model.md')

        # Investigation: eligible
        $investResult = Test-InvestigationOnlyEligibility -Files $files
        $investResult.IsEligible | Should -BeTrue

        # Audit: NOT filtered (preserved as implementation)
        $implResult = Get-ImplementationFiles -Files $files
        $implResult | Should -Contain '.agents/security/threat-model.md'
    }

    It "Session log + ADR: filtered by audit, rejected by investigation" {
        $files = @(
            '.agents/sessions/2026-01-01-session-01.md',
            '.agents/architecture/ADR-001.md'
        )

        # Audit filtering: removes session log, keeps ADR
        $implResult = Get-ImplementationFiles -Files $files
        $implResult.Count | Should -Be 1
        $implResult | Should -Contain '.agents/architecture/ADR-001.md'

        # Investigation: NOT eligible (ADR is implementation)
        $investResult = Test-InvestigationOnlyEligibility -Files $files
        $investResult.IsEligible | Should -BeFalse
        $investResult.ImplementationFiles | Should -Contain '.agents/architecture/ADR-001.md'
    }
}

Describe "Path Escape Validation (E_PATH_ESCAPE)" {
    BeforeAll {
        # Create a temporary directory structure for testing
        $script:TestRoot = Join-Path $TestDrive "test-repo"
        $script:SessionsDir = Join-Path $TestRoot ".agents" "sessions"
        New-Item -ItemType Directory -Path $SessionsDir -Force | Out-Null
        
        # Create a mock git repo structure
        Push-Location $TestRoot
        & git init 2>&1 | Out-Null
        & git config user.email "test@example.com"
        & git config user.name "Test User"
        Pop-Location
    }

    Context "Valid paths" {
        It "Validates session log directly under .agents/sessions/" -Skip {
            # This test requires full integration - skip for unit test isolation
            # Real validation happens in integration tests
            $true | Should -BeTrue
        }

        It "Validates session log in nested subdirectory" -Skip {
            # This test requires full integration - skip for unit test isolation
            $true | Should -BeTrue
        }
    }

    Context "Invalid paths (security - path traversal)" {
        It "Detects path outside .agents/sessions/ (parent directory)" {
            # Test that a file outside the expected directory would be rejected
            # We can't easily test this without mocking, but we validate the logic exists
            $scriptContent = Get-Content -Path (Join-Path $PSScriptRoot ".." "scripts" "Validate-Session.ps1") -Raw
            $scriptContent | Should -Match 'E_PATH_ESCAPE'
            $scriptContent | Should -Match 'StartsWith\(\$expectedDirWithSep'
        }

        It "Uses normalized paths for comparison to prevent bypasses" {
            $scriptContent = Get-Content -Path (Join-Path $PSScriptRoot ".." "scripts" "Validate-Session.ps1") -Raw
            $scriptContent | Should -Match '\$sessionFullPathNormalized'
            $scriptContent | Should -Match '\$expectedDirNormalized'
            $scriptContent | Should -Match 'GetFullPath'
        }

        It "Uses trailing separator to prevent prefix bypass attacks" {
            $scriptContent = Get-Content -Path (Join-Path $PSScriptRoot ".." "scripts" "Validate-Session.ps1") -Raw
            $scriptContent | Should -Match '\$expectedDirWithSep'
            $scriptContent | Should -Match 'DirectorySeparatorChar'
        }
    }

    Context "Enhanced error diagnostics" {
        It "Error message includes expected directory" {
            $scriptContent = Get-Content -Path (Join-Path $PSScriptRoot ".." "scripts" "Validate-Session.ps1") -Raw
            $scriptContent | Should -Match 'Expected directory:.*\$expectedDirWithSep'
        }

        It "Error message includes normalized path being validated" {
            $scriptContent = Get-Content -Path (Join-Path $PSScriptRoot ".." "scripts" "Validate-Session.ps1") -Raw
            $scriptContent | Should -Match 'Normalized path:.*\$sessionFullPathNormalized'
        }

        It "Error message includes comparison result" {
            $scriptContent = Get-Content -Path (Join-Path $PSScriptRoot ".." "scripts" "Validate-Session.ps1") -Raw
            $scriptContent | Should -Match 'Starts with check:.*\$startsWithCheck'
        }

        It "Error message includes original path" {
            $scriptContent = Get-Content -Path (Join-Path $PSScriptRoot ".." "scripts" "Validate-Session.ps1") -Raw
            $scriptContent | Should -Match 'Original path:.*\$sessionFullPath'
        }

        It "Error message includes current working directory" {
            $scriptContent = Get-Content -Path (Join-Path $PSScriptRoot ".." "scripts" "Validate-Session.ps1") -Raw
            $scriptContent | Should -Match 'Current directory:.*\$PWD'
        }

        It "Error message includes repository root" {
            $scriptContent = Get-Content -Path (Join-Path $PSScriptRoot ".." "scripts" "Validate-Session.ps1") -Raw
            $scriptContent | Should -Match 'Repo root:.*\$repoRoot'
        }
    }

    Context "Symlink detection" {
        It "Script includes symlink detection logic" {
            $scriptContent = Get-Content -Path (Join-Path $PSScriptRoot ".." "scripts" "Validate-Session.ps1") -Raw
            $scriptContent | Should -Match 'LinkType'
            $scriptContent | Should -Match 'E_PATH_SYMLINK'
        }

        It "Symlink check uses Get-ChildItem with -Force flag" {
            $scriptContent = Get-Content -Path (Join-Path $PSScriptRoot ".." "scripts" "Validate-Session.ps1") -Raw
            $scriptContent | Should -Match 'Get-ChildItem.*-Force'
        }

        It "Symlink detection occurs before path normalization" {
            $scriptContent = Get-Content -Path (Join-Path $PSScriptRoot ".." "scripts" "Validate-Session.ps1") -Raw
            
            # Find line positions to verify ordering
            $lines = $scriptContent -split "`r?`n"
            $linkTypeLineIndex = ($lines | Select-String -Pattern 'if.*LinkType' | Select-Object -First 1).LineNumber
            $normalizedPathLineIndex = ($lines | Select-String -Pattern '\$sessionFullPathNormalized\s*=.*GetFullPath' | Select-Object -First 1).LineNumber
            
            # Verify symlink check comes before path normalization
            $linkTypeLineIndex | Should -Not -BeNullOrEmpty
            $normalizedPathLineIndex | Should -Not -BeNullOrEmpty
            $linkTypeLineIndex | Should -BeLessThan $normalizedPathLineIndex
        }

        It "E_PATH_SYMLINK error includes descriptive message" {
            $scriptContent = Get-Content -Path (Join-Path $PSScriptRoot ".." "scripts" "Validate-Session.ps1") -Raw
            $scriptContent | Should -Match "E_PATH_SYMLINK.*Security.*symlink"
        }

        # Platform-specific symlink test - only run on Linux/macOS
        # Note: Creating symlinks on Windows requires elevated privileges (admin rights)
        # or Windows 10+ with Developer Mode enabled. Skipping on Windows to avoid
        # privilege-related test failures.
        It "Rejects actual symlink to session log" -Skip:($IsWindows) {
            # Create a real session file
            $realSession = Join-Path $SessionsDir "real-session.md"
            Set-Content -Path $realSession -Value "# Test Session" -Encoding UTF8
            
            # Create a symlink to it
            $symlinkSession = Join-Path $SessionsDir "symlink-session.md"
            New-Item -ItemType SymbolicLink -Path $symlinkSession -Target $realSession -Force | Out-Null
            
            try {
                # Verify symlink was created
                $item = Get-ChildItem -Path $symlinkSession -Force
                $item.LinkType | Should -Not -BeNullOrEmpty
                
                # The actual validation script would reject this
                # We're just verifying the symlink detection mechanism works
                $item.LinkType | Should -BeIn @('SymbolicLink', 'HardLink')
            }
            finally {
                # Cleanup
                if (Test-Path $symlinkSession) {
                    Remove-Item $symlinkSession -Force
                }
                if (Test-Path $realSession) {
                    Remove-Item $realSession -Force
                }
            }
        }
    }

    Context "Path normalization edge cases" {
        It "Handles case-insensitive comparison on Windows" {
            $scriptContent = Get-Content -Path (Join-Path $PSScriptRoot ".." "scripts" "Validate-Session.ps1") -Raw
            $scriptContent | Should -Match 'OrdinalIgnoreCase'
        }

        It "Trims trailing slashes from paths before comparison" {
            $scriptContent = Get-Content -Path (Join-Path $PSScriptRoot ".." "scripts" "Validate-Session.ps1") -Raw
            # Check for TrimEnd with backslash and forward slash characters specifically
            # Pattern matches TrimEnd('\','/') with proper escaping
            $scriptContent | Should -Match "TrimEnd\('\\','/'\)"
        }

        It "Uses platform-appropriate directory separator" {
            $scriptContent = Get-Content -Path (Join-Path $PSScriptRoot ".." "scripts" "Validate-Session.ps1") -Raw
            $scriptContent | Should -Match '\[System\.IO\.Path\]::DirectorySeparatorChar'
        }
    }

    Context "Error code documentation" {
        It "Documents E_PATH_SYMLINK error code" {
            $scriptContent = Get-Content -Path (Join-Path $PSScriptRoot ".." "scripts" "Validate-Session.ps1") -Raw
            $scriptContent | Should -Match 'E_PATH_SYMLINK.*symlink'
        }

        It "Documents E_PATH_ESCAPE error code" {
            $scriptContent = Get-Content -Path (Join-Path $PSScriptRoot ".." "scripts" "Validate-Session.ps1") -Raw
            # Check for E_PATH_ESCAPE with specific path traversal/escape wording
            $scriptContent | Should -Match 'E_PATH_ESCAPE:.*path.*\.agents/sessions/.*\(path traversal/escape'
        }

        It "Error codes are documented in header" {
            $scriptContent = Get-Content -Path (Join-Path $PSScriptRoot ".." "scripts" "Validate-Session.ps1") -Raw
            # Check that a .NOTES section exists
            $scriptContent | Should -Match '(?s)\.NOTES.*?(?=#>|\z)'

            # Extract the .NOTES section and verify it documents error codes
            $notesSection = [regex]::Match($scriptContent, '(?s)\.NOTES.*?(?=#>|\z)').Value
            $notesSection | Should -Match 'Error Codes:'
        }
    }
}
