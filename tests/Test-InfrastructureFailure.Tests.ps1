BeforeAll {
    $script:TestScript = "$PSScriptRoot/../.github/actions/ai-review/test-infrastructure-failure.sh"
}

Describe 'is_infrastructure_failure Function Tests' {
    BeforeEach {
        # Ensure script is executable
        if ($IsLinux -or $IsMacOS) {
            chmod +x $script:TestScript 2>$null
        }
    }

    Context 'Timeout Detection (Exit Code 124)' {
        It 'Returns true for exit code 124 (timeout)' {
            # Arrange & Act
            $result = bash $script:TestScript 124 "" ""

            # Assert
            $result | Should -Be "true"
        }

        It 'Returns true for timeout even with output present' {
            # Arrange & Act
            $result = bash $script:TestScript 124 "some output" ""

            # Assert
            $result | Should -Be "true"
        }

        It 'Returns true for timeout even with stderr present' {
            # Arrange & Act
            $result = bash $script:TestScript 124 "" "some error"

            # Assert
            $result | Should -Be "true"
        }
    }

    Context 'Auth Failure Detection (No Output)' {
        It 'Returns true for exit code 1 with no stdout and no stderr' {
            # Arrange & Act
            $result = bash $script:TestScript 1 "" ""

            # Assert
            $result | Should -Be "true"
        }

        It 'Returns true for any non-zero exit with no output' {
            # Arrange & Act
            $result = bash $script:TestScript 2 "" ""

            # Assert
            $result | Should -Be "true"
        }

        It 'Returns false for exit code 0 with no output (success case)' {
            # Arrange & Act
            $result = bash $script:TestScript 0 "" ""

            # Assert
            $result | Should -Be "false"
        }

        It 'Returns false for non-zero exit WITH stdout' {
            # Arrange & Act - code quality failure has output
            $result = bash $script:TestScript 1 "VERDICT: CRITICAL_FAIL" ""

            # Assert
            $result | Should -Be "false"
        }
    }

    Context 'Infrastructure Keywords in Stderr' {
        It 'Detects rate limit errors' {
            # Arrange & Act
            $result = bash $script:TestScript 1 "" "Error: rate limit exceeded"

            # Assert
            $result | Should -Be "true"
        }

        It 'Detects timeout keyword in stderr' {
            # Arrange & Act
            $result = bash $script:TestScript 1 "" "Request timeout after 30s"

            # Assert
            $result | Should -Be "true"
        }

        It 'Detects network error' {
            # Arrange & Act
            $result = bash $script:TestScript 1 "" "network error: unable to connect"

            # Assert
            $result | Should -Be "true"
        }

        It 'Detects connection refused (ECONNREFUSED)' {
            # Arrange & Act
            $result = bash $script:TestScript 1 "" "Error: ECONNREFUSED"

            # Assert
            $result | Should -Be "true"
        }

        It 'Detects connection reset' {
            # Arrange & Act
            $result = bash $script:TestScript 1 "" "connection reset by peer"

            # Assert
            $result | Should -Be "true"
        }

        It 'Detects ETIMEDOUT' {
            # Arrange & Act
            $result = bash $script:TestScript 1 "" "Error: ETIMEDOUT"

            # Assert
            $result | Should -Be "true"
        }

        It 'Detects HTTP 502 Bad Gateway' {
            # Arrange & Act
            $result = bash $script:TestScript 1 "" "HTTP 502 Bad Gateway"

            # Assert
            $result | Should -Be "true"
        }

        It 'Detects HTTP 503 Service Unavailable' {
            # Arrange & Act
            $result = bash $script:TestScript 1 "" "503 Service Unavailable"

            # Assert
            $result | Should -Be "true"
        }

        It 'Detects HTTP 504 Gateway Timeout' {
            # Arrange & Act
            $result = bash $script:TestScript 1 "" "504 Gateway Timeout"

            # Assert
            $result | Should -Be "true"
        }

        It 'Is case-insensitive for keywords' {
            # Arrange & Act
            $result = bash $script:TestScript 1 "" "RATE LIMIT exceeded"

            # Assert
            $result | Should -Be "true"
        }
    }

    Context 'Code Quality Failures (Not Infrastructure)' {
        It 'Returns false for non-zero exit with stdout output' {
            # Arrange & Act - legitimate code quality failure
            $result = bash $script:TestScript 1 "VERDICT: CRITICAL_FAIL - Security issues found" ""

            # Assert
            $result | Should -Be "false"
        }

        It 'Returns false for non-zero exit with non-infra stderr' {
            # Arrange & Act - application error, not infrastructure
            $result = bash $script:TestScript 1 "" "Error: Invalid prompt format"

            # Assert
            $result | Should -Be "false"
        }

        It 'Returns false for successful execution' {
            # Arrange & Act
            $result = bash $script:TestScript 0 "VERDICT: PASS" ""

            # Assert
            $result | Should -Be "false"
        }

        It 'Returns false for code error with detailed stderr' {
            # Arrange & Act - syntax error in prompt, not infrastructure
            $result = bash $script:TestScript 1 "" "Syntax error in JSON at position 42"

            # Assert
            $result | Should -Be "false"
        }
    }

    Context 'Edge Cases' {
        It 'Handles empty strings correctly' {
            # Arrange & Act - exit 0 with empties = success
            $result = bash $script:TestScript 0 "" ""

            # Assert
            $result | Should -Be "false"
        }

        It 'Handles whitespace-only output as empty' {
            # Arrange & Act - whitespace should not count as output
            # Note: bash [ -z ] treats whitespace as non-empty
            $result = bash $script:TestScript 1 "   " ""

            # Assert - has output (whitespace), so not infra failure
            $result | Should -Be "false"
        }

        It 'Handles stderr with multiple infrastructure keywords' {
            # Arrange & Act
            $result = bash $script:TestScript 1 "" "rate limit and timeout and 503"

            # Assert
            $result | Should -Be "true"
        }

        It 'Handles large exit codes' {
            # Arrange & Act
            $result = bash $script:TestScript 255 "" ""

            # Assert - non-zero with no output = infrastructure
            $result | Should -Be "true"
        }
    }
}
