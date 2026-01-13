BeforeAll {
    $script:TestScript = "$PSScriptRoot/../.github/actions/ai-review/test-large-pr-handling.sh"
}

Describe 'Large PR Handling Logic Tests' {
    BeforeEach {
        # Ensure script is executable
        if ($IsLinux -or $IsMacOS) {
            chmod +x $script:TestScript 2>$null
        }
    }

    Context 'HTTP 406 Error Handling (>300 files)' {
        It 'Handles PR with <500 files successfully via pagination' {
            # Arrange & Act - 350 files, pagination should work
            $result = bash $script:TestScript http_406 350 5 | ConvertFrom-Json

            # Assert
            $result.context_mode | Should -Be "summary"
            $result.exit_code | Should -Be 0
            $result.warning | Should -BeNullOrEmpty
        }

        It 'Issues warning when file list truncated at 500 files' {
            # Arrange & Act - 600 files, should hit MAX_PAGES limit
            $result = bash $script:TestScript http_406 600 5 | ConvertFrom-Json

            # Assert
            $result.context_mode | Should -Be "summary"
            $result.exit_code | Should -Be 0
            $result.warning | Should -BeLike "*truncated at 500 files*"
        }

        It 'Issues warning when file list truncated at exactly 500 files' {
            # Arrange & Act - 501 files, just over the limit
            $result = bash $script:TestScript http_406 501 5 | ConvertFrom-Json

            # Assert
            $result.context_mode | Should -Be "summary"
            $result.exit_code | Should -Be 0
            $result.warning | Should -BeLike "*truncated at 500 files*"
        }

        It 'Does not warn for PR with exactly 500 files' {
            # Arrange & Act - exactly 500 files
            $result = bash $script:TestScript http_406 500 5 | ConvertFrom-Json

            # Assert
            $result.context_mode | Should -Be "summary"
            $result.exit_code | Should -Be 0
            $result.warning | Should -BeNullOrEmpty
        }

        It 'Handles PR with 300 files (at GitHub limit)' {
            # Arrange & Act - exactly at GitHub's 300 file limit
            $result = bash $script:TestScript http_406 300 5 | ConvertFrom-Json

            # Assert
            $result.context_mode | Should -Be "summary"
            $result.exit_code | Should -Be 0
            $result.warning | Should -BeNullOrEmpty
        }

        It 'Sets context_mode to summary for HTTP 406' {
            # Arrange & Act
            $result = bash $script:TestScript http_406 350 5 | ConvertFrom-Json

            # Assert
            $result.context_mode | Should -Be "summary"
        }

        It 'Includes appropriate context message for large PR' {
            # Arrange & Act
            $result = bash $script:TestScript http_406 350 5 | ConvertFrom-Json

            # Assert
            $result.context_preview | Should -BeLike "*Large PR*"
            $result.context_preview | Should -BeLike "*>300 files*"
        }
    }

    Context 'Fallback Strategy Tests' {
        It 'Falls back to --name-only when API pagination fails' {
            # Arrange & Act
            $result = bash $script:TestScript api_pagination_failure 0 5 | ConvertFrom-Json

            # Assert
            $result.context_mode | Should -Be "summary"
            $result.exit_code | Should -Be 0
            $result.context_preview | Should -BeLike "*Large PR*"
        }

        It 'Fails with exit code 1 when all fallbacks fail' {
            # Arrange & Act
            $result = bash $script:TestScript all_fallbacks_fail 0 5 | ConvertFrom-Json

            # Assert
            $result.exit_code | Should -Be 1
        }
    }

    Context 'Normal PR Handling' {
        It 'Handles normal-sized diff without pagination' {
            # Arrange & Act
            $result = bash $script:TestScript normal_diff 0 5 | ConvertFrom-Json

            # Assert
            $result.context_mode | Should -Be "full"
            $result.exit_code | Should -Be 0
            $result.warning | Should -BeNullOrEmpty
        }

        It 'Switches to summary mode for large line count' {
            # Arrange & Act
            $result = bash $script:TestScript large_diff 0 5 | ConvertFrom-Json

            # Assert
            $result.context_mode | Should -Be "summary"
            $result.exit_code | Should -Be 0
        }
    }

    Context 'MAX_PAGES Configuration' {
        It 'Respects custom MAX_PAGES limit' {
            # Arrange & Act - 350 files, MAX_PAGES=3 (300 files max)
            $result = bash $script:TestScript http_406 350 3 | ConvertFrom-Json

            # Assert
            $result.warning | Should -BeLike "*truncated at 300 files*"
        }

        It 'Works with MAX_PAGES=1' {
            # Arrange & Act - 150 files, MAX_PAGES=1 (100 files max)
            $result = bash $script:TestScript http_406 150 1 | ConvertFrom-Json

            # Assert
            $result.warning | Should -BeLike "*truncated at 100 files*"
        }

        It 'Handles MAX_PAGES=10' {
            # Arrange & Act - 900 files, MAX_PAGES=10 (1000 files max)
            $result = bash $script:TestScript http_406 900 10 | ConvertFrom-Json

            # Assert
            $result.exit_code | Should -Be 0
            $result.warning | Should -BeNullOrEmpty
        }
    }

    Context 'Edge Cases' {
        It 'Handles PR with 0 files' {
            # Arrange & Act
            $result = bash $script:TestScript http_406 0 5 | ConvertFrom-Json

            # Assert
            $result.exit_code | Should -Be 1
        }

        It 'Handles very large PR (10000 files)' {
            # Arrange & Act - should truncate at 500
            $result = bash $script:TestScript http_406 10000 5 | ConvertFrom-Json

            # Assert
            $result.context_mode | Should -Be "summary"
            $result.exit_code | Should -Be 0
            $result.warning | Should -BeLike "*truncated at 500 files*"
        }

        It 'Handles single file PR' {
            # Arrange & Act
            $result = bash $script:TestScript http_406 1 5 | ConvertFrom-Json

            # Assert
            $result.context_mode | Should -Be "summary"
            $result.exit_code | Should -Be 0
            $result.warning | Should -BeNullOrEmpty
        }
    }

    Context 'Warning Message Format' {
        It 'Warning message includes correct file count' {
            # Arrange & Act - 600 files with MAX_PAGES=5
            $result = bash $script:TestScript http_406 600 5 | ConvertFrom-Json

            # Assert
            $result.warning | Should -BeLike "*500 files*"
        }

        It 'Warning message is informative' {
            # Arrange & Act
            $result = bash $script:TestScript http_406 600 5 | ConvertFrom-Json

            # Assert
            $result.warning | Should -BeLike "*truncated*"
            $result.warning | Should -BeLike "*files*"
        }
    }
}
