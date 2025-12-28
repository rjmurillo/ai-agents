<#
.SYNOPSIS
    Tests for Validate-PRDescription.ps1

.DESCRIPTION
    Pester tests covering URL parsing, file extraction from descriptions,
    mismatch detection, and CI mode behavior.
#>

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot '..' 'Validate-PRDescription.ps1'
    $ScriptContent = Get-Content -Path $ScriptPath -Raw
}

Describe 'Validate-PRDescription.ps1' {
    Context 'Script Syntax' {
        It 'Should be valid PowerShell' {
            $errors = $null
            [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$errors)
            $errors | Should -BeNullOrEmpty
        }

        It 'Should have comment-based help' {
            $ScriptContent | Should -Match '\.SYNOPSIS'
            $ScriptContent | Should -Match '\.DESCRIPTION'
            $ScriptContent | Should -Match '\.PARAMETER'
            $ScriptContent | Should -Match '\.EXAMPLE'
        }
    }

    Context 'Parameter Definitions' {
        BeforeAll {
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
            $paramBlock = $ast.ParamBlock
        }

        It 'Should have mandatory PRNumber parameter' {
            $ScriptContent | Should -Match '\[Parameter\(Mandatory\s*=\s*\$true\)\]'
            $ScriptContent | Should -Match '\[int\]\$PRNumber'
        }

        It 'Should have optional Owner parameter' {
            $ScriptContent | Should -Match '\[string\]\$Owner\s*=\s*""'
        }

        It 'Should have optional Repo parameter' {
            $ScriptContent | Should -Match '\[string\]\$Repo\s*=\s*""'
        }

        It 'Should have CI switch parameter' {
            $ScriptContent | Should -Match '\[switch\]\$CI'
        }
    }

    Context 'Get-RepoInfo Function' {
        It 'Should define Get-RepoInfo function' {
            $ScriptContent | Should -Match 'function\s+Get-RepoInfo'
        }

        It 'Should parse HTTPS GitHub URLs' {
            # Pattern: github.com[:/]([^/]+)/([^/\.]+)
            $pattern = 'github\.com[:/]([^/]+)/([^/\.]+)'
            'https://github.com/owner/repo.git' -match $pattern | Should -BeTrue
            $Matches[1] | Should -Be 'owner'
            $Matches[2] | Should -Be 'repo'
        }

        It 'Should parse SSH GitHub URLs' {
            $pattern = 'github\.com[:/]([^/]+)/([^/\.]+)'
            'git@github.com:owner/repo.git' -match $pattern | Should -BeTrue
            $Matches[1] | Should -Be 'owner'
            $Matches[2] | Should -Be 'repo'
        }

        It 'Should parse HTTPS URLs without .git suffix' {
            $pattern = 'github\.com[:/]([^/]+)/([^/\.]+)'
            'https://github.com/rjmurillo/ai-agents' -match $pattern | Should -BeTrue
            $Matches[1] | Should -Be 'rjmurillo'
            $Matches[2] | Should -Be 'ai-agents'
        }
    }

    Context 'File Pattern Extraction' {
        # Test the regex patterns used to extract file mentions from descriptions

        It 'Should extract inline code file mentions' {
            $pattern = '`([^`]+\.(ps1|md|yml|yaml|json|cs|ts|js|py|sh|bash))`'
            $text = 'Modified `scripts/Test.ps1` and `config.json`'
            $matches = [regex]::Matches($text, $pattern)
            $matches.Count | Should -Be 2
            $matches[0].Groups[1].Value | Should -Be 'scripts/Test.ps1'
            $matches[1].Groups[1].Value | Should -Be 'config.json'
        }

        It 'Should extract bold file mentions' {
            $pattern = '\*\*([^*]+\.(ps1|md|yml|yaml|json|cs|ts|js|py|sh|bash))\*\*'
            $text = 'Changed **workflow.yml** for CI'
            $matches = [regex]::Matches($text, $pattern)
            $matches.Count | Should -Be 1
            $matches[0].Groups[1].Value | Should -Be 'workflow.yml'
        }

        It 'Should extract list item file mentions' {
            $pattern = '^\s*[-*+]\s+([^\s]+\.(ps1|md|yml|yaml|json|cs|ts|js|py|sh|bash))'
            $text = "- script.ps1`n* config.yml`n+ README.md"
            $matches = [regex]::Matches($text, $pattern, [System.Text.RegularExpressions.RegexOptions]::Multiline)
            $matches.Count | Should -Be 3
        }

        It 'Should extract markdown link file mentions' {
            $pattern = '\[([^\]]+\.(ps1|md|yml|yaml|json|cs|ts|js|py|sh|bash))\]'
            $text = 'See [docs/guide.md] for details'
            $matches = [regex]::Matches($text, $pattern)
            $matches.Count | Should -Be 1
            $matches[0].Groups[1].Value | Should -Be 'docs/guide.md'
        }

        It 'Should handle multiple patterns in same text' {
            # Test inline code and markdown link patterns together
            $description = @"
## Changes
Modified ``scripts/Main.ps1`` for the main logic.
See [README.md] for documentation.
"@
            $allMatches = @()
            $patterns = @(
                '`([^`]+\.(ps1|md|yml|yaml|json|cs|ts|js|py|sh|bash))`',
                '\[([^\]]+\.(ps1|md|yml|yaml|json|cs|ts|js|py|sh|bash))\]'
            )
            foreach ($pattern in $patterns) {
                $regexMatches = [regex]::Matches($description, $pattern)
                foreach ($regexMatch in $regexMatches) {
                    $allMatches += $regexMatch.Groups[1].Value
                }
            }
            $allMatches.Count | Should -Be 2
            $allMatches | Should -Contain 'scripts/Main.ps1'
            $allMatches | Should -Contain 'README.md'
        }
    }

    Context 'Path Normalization' {
        It 'Should normalize backslashes to forward slashes' {
            $file = 'scripts\subdir\test.ps1' -replace '\\', '/'
            $file | Should -Be 'scripts/subdir/test.ps1'
        }

        It 'Should remove leading ./' {
            $file = './scripts/test.ps1' -replace '^\./', ''
            $file | Should -Be 'scripts/test.ps1'
        }
    }

    Context 'File Matching Logic' {
        It 'Should match exact file paths' {
            $actual = 'scripts/Validate-PRDescription.ps1'
            $mentioned = 'scripts/Validate-PRDescription.ps1'
            ($actual -eq $mentioned) | Should -BeTrue
        }

        It 'Should match suffix with forward slash' {
            $actual = 'scripts/tests/Validate-PRDescription.Tests.ps1'
            $mentioned = 'Validate-PRDescription.Tests.ps1'
            ($actual -like "*/$mentioned") | Should -BeTrue
        }

        It 'Should match suffix with backslash' {
            $actual = 'scripts\tests\Validate-PRDescription.Tests.ps1'
            $mentioned = 'Validate-PRDescription.Tests.ps1'
            ($actual -like "*\$mentioned") | Should -BeTrue
        }

        It 'Should not match partial names' {
            $actual = 'scripts/Validate-PRDescription.ps1'
            $mentioned = 'Description.ps1'
            $match = ($actual -eq $mentioned -or $actual -like "*/$mentioned" -or $actual -like "*\$mentioned")
            $match | Should -BeFalse
        }
    }

    Context 'Significant File Detection' {
        It 'Should identify significant extensions' {
            $significantExtensions = @('.ps1', '.cs', '.ts', '.js', '.py', '.yml', '.yaml')

            [IO.Path]::GetExtension('script.ps1') -in $significantExtensions | Should -BeTrue
            [IO.Path]::GetExtension('config.yml') -in $significantExtensions | Should -BeTrue
            [IO.Path]::GetExtension('app.ts') -in $significantExtensions | Should -BeTrue
            [IO.Path]::GetExtension('readme.md') -in $significantExtensions | Should -BeFalse
        }

        It 'Should identify key directories' {
            $keyDirPattern = '^(\.github|scripts|src|\.agents)'

            '.github/workflows/ci.yml' -match $keyDirPattern | Should -BeTrue
            'scripts/test.ps1' -match $keyDirPattern | Should -BeTrue
            'src/main.cs' -match $keyDirPattern | Should -BeTrue
            '.agents/planning/spec.md' -match $keyDirPattern | Should -BeTrue
            'docs/readme.md' -match $keyDirPattern | Should -BeFalse
            'lib/utils.js' -match $keyDirPattern | Should -BeFalse
        }
    }

    Context 'Issue Classification' {
        It 'Should classify mentioned-but-not-in-diff as CRITICAL' {
            # Script creates issues with Severity = "CRITICAL" for this case
            $ScriptContent | Should -Match 'Severity\s*=\s*"CRITICAL"[\s\S]*?Type\s*=\s*"File mentioned but not in diff"'
        }

        It 'Should classify not-mentioned as WARNING' {
            # Script creates issues with Severity = "WARNING" for this case
            $ScriptContent | Should -Match 'Severity\s*=\s*"WARNING"[\s\S]*?Type\s*=\s*"Significant file not mentioned"'
        }
    }

    Context 'Exit Codes' {
        It 'Should define exit 0 for success' {
            $ScriptContent | Should -Match 'exit\s+0'
        }

        It 'Should define exit 1 for critical issues in CI mode' {
            $ScriptContent | Should -Match 'if\s*\(\$CI\)\s*\{\s*exit\s+1\s*\}'
        }

        It 'Should define exit 2 for infrastructure errors' {
            $ScriptContent | Should -Match 'exit\s+2'
        }
    }

    Context 'gh CLI Integration' {
        It 'Should check for gh CLI availability' {
            $ScriptContent | Should -Match 'Get-Command\s+gh'
        }

        It 'Should fetch PR with required fields' {
            $ScriptContent | Should -Match 'gh\s+pr\s+view.*--json\s+title,body,files'
        }

        It 'Should support repo override' {
            $ScriptContent | Should -Match '--repo\s+"\$Owner/\$Repo"'
        }

        It 'Should check LASTEXITCODE after gh commands' {
            $ScriptContent | Should -Match '\$LASTEXITCODE\s*-ne\s*0'
        }
    }

    Context 'Array Handling' {
        It 'Should wrap files array with @() for safety' {
            # PowerShell gotcha: single-item arrays become scalars
            $ScriptContent | Should -Match '@\(\$pr\.files'
        }

        It 'Should wrap mentionedFiles with @() after Select-Object' {
            $ScriptContent | Should -Match '@\(\$mentionedFiles\s*\|\s*Select-Object'
        }

        It 'Should wrap issues filter with @() for count' {
            $ScriptContent | Should -Match '@\(\$issues\s*\|\s*Where-Object'
        }
    }

    Context 'Output Messages' {
        It 'Should output success message' {
            $ScriptContent | Should -Match 'PR description matches diff'
        }

        It 'Should output critical count' {
            $ScriptContent | Should -Match 'CRITICAL:'
        }

        It 'Should output warning count' {
            $ScriptContent | Should -Match 'WARNING:'
        }

        It 'Should use color output for severity' {
            $ScriptContent | Should -Match '-ForegroundColor\s+Red'
            $ScriptContent | Should -Match '-ForegroundColor\s+Yellow'
        }
    }

    Context 'Error Handling' {
        It 'Should use StrictMode' {
            $ScriptContent | Should -Match 'Set-StrictMode\s+-Version\s+Latest'
        }

        It 'Should set ErrorActionPreference to Stop' {
            $ScriptContent | Should -Match "\`$ErrorActionPreference\s*=\s*'Stop'"
        }

        It 'Should throw on invalid remote URL' {
            $ScriptContent | Should -Match 'throw\s+"Could not parse GitHub owner/repo'
        }
    }
}
