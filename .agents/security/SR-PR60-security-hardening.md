# Security Hardening Report: PR #60 Remediation Plan

> **Status**: Review Complete
> **Date**: 2025-12-18
> **Reviewer**: Security Agent
> **Scope**: Security gaps in PR #60 remediation plan

---

## Executive Summary

The PR #60 remediation plan addresses security gaps but contains INSUFFICIENT specificity for implementation. This report provides EXACT code, regex patterns, test payloads, and implementation details required for secure remediation.

| Finding | Severity | Status |
|---------|----------|--------|
| Regex validation inadequate | CRITICAL | Requires revision |
| Test payloads incomplete | HIGH | Requires addition |
| AllowedBase strategy undefined | HIGH | Requires specification |
| Token security unaddressed | MEDIUM | Missing from plan |
| Threat model incomplete | HIGH | Missing from plan |

---

## 1. Command Injection Prevention (GAP-SEC-001)

### 1.1 Proposed Regex Analysis

The plan proposes `'^[\w\-\.\s]+$'` for label validation. This is **INADEQUATE**.

#### Problems with Proposed Regex

| Issue | Risk | Example Payload |
|-------|------|-----------------|
| `\w` includes underscore | Low | Generally safe |
| `\s` allows newlines | CRITICAL | `"valid\nrm -rf /"` |
| No length limit | MEDIUM | DoS via extremely long labels |
| Unicode not addressed | HIGH | `"vаlid"` (Cyrillic 'а' U+0430) |
| PowerShell escaping | HIGH | `"label`$(whoami)"` |

#### Corrected Regex for GitHub Labels

```powershell
# GitHub label constraints:
# - 1-50 characters
# - Cannot start/end with whitespace
# - Cannot contain newlines
# - Should be ASCII printable only for safety

$LabelPattern = '^[a-zA-Z0-9][a-zA-Z0-9 _\-\.]{0,48}[a-zA-Z0-9]?$'

# Or for single character labels:
$LabelPatternFull = '^(?:[a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9 _\-\.]{0,48}[a-zA-Z0-9])$'
```

#### Shell Expansion in `gh issue edit`

The plan's PowerShell approach using `$env:ISSUE_NUMBER` is safer than bash variable expansion, BUT the label value still passes through shell interpretation.

**CRITICAL**: The `gh issue edit` command internally processes the label. Even with PowerShell, certain characters can cause issues.

##### Secure Implementation

```powershell
- name: Parse and Apply Labels
  shell: pwsh
  env:
    ISSUE_NUMBER: ${{ github.event.issue.number }}
    RAW_OUTPUT: ${{ steps.categorize.outputs.response }}
  run: |
    # Strict label validation regex
    # - ASCII alphanumeric start/end
    # - Internal: letters, digits, spaces, hyphens, underscores, periods
    # - Length: 1-50 characters
    # - NO newlines, NO shell metacharacters
    $ValidLabelPattern = '^[a-zA-Z0-9](?:[a-zA-Z0-9 _\-\.]{0,48}[a-zA-Z0-9])?$|^[a-zA-Z0-9]$'

    # Dangerous character blocklist (defense in depth)
    $DangerousChars = '[`$;|&<>(){}[\]''"\x00-\x1F\x7F-\xFF]'

    $rawOutput = $env:RAW_OUTPUT
    $labels = @()

    if ($rawOutput -match '"labels"\s*:\s*\[([^\]]+)\]') {
        $rawLabels = $Matches[1] -split ',' | ForEach-Object {
            $_.Trim().Trim('"').Trim()
        } | Where-Object { $_ -ne '' }

        foreach ($label in $rawLabels) {
            # Check for dangerous characters first
            if ($label -match $DangerousChars) {
                Write-Warning "SECURITY: Rejected label with dangerous characters: [REDACTED]"
                continue
            }

            # Validate against allowed pattern
            if ($label -notmatch $ValidLabelPattern) {
                Write-Warning "Skipping invalid label format: $label"
                continue
            }

            # Length check (redundant with regex but explicit)
            if ($label.Length -gt 50 -or $label.Length -lt 1) {
                Write-Warning "Skipping label with invalid length: $label"
                continue
            }

            $labels += $label
        }
    }

    # Apply validated labels
    $failedLabels = @()
    foreach ($label in $labels) {
        Write-Host "Adding label: $label"

        # Use --repo to be explicit, quote the label
        $result = gh issue edit $env:ISSUE_NUMBER --repo "$env:GITHUB_REPOSITORY" --add-label "$label" 2>&1

        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Failed to add label '$label': $result"
            $failedLabels += $label
        }
    }

    # Report summary
    if ($failedLabels.Count -gt 0) {
        Write-Host "::warning::Failed to add $($failedLabels.Count) label(s): $($failedLabels -join ', ')"
    }

    Write-Host "Labels applied successfully: $($labels.Count - $failedLabels.Count) of $($labels.Count)"
```

#### Unicode Homoglyph Defense

```powershell
function Test-AsciiOnly {
    <#
    .SYNOPSIS
        Validates string contains only ASCII printable characters.
    .DESCRIPTION
        Prevents Unicode homoglyph attacks by rejecting non-ASCII.
    #>
    [CmdletBinding()]
    [OutputType([bool])]
    param(
        [Parameter(Mandatory)]
        [string]$Value
    )

    # ASCII printable: 0x20-0x7E (space through tilde)
    return $Value -match '^[\x20-\x7E]+$'
}

# Usage in label validation:
if (-not (Test-AsciiOnly -Value $label)) {
    Write-Warning "SECURITY: Rejected label with non-ASCII characters"
    continue
}
```

---

## 2. Security Function Test Cases (GAP-SEC-002)

### 2.1 Complete Test Suite for `Test-GitHubNameValid`

```powershell
Describe "Test-GitHubNameValid - Security Boundary Tests" {

    Context "Owner Validation - Valid Cases" {
        @(
            @{ Name = 'octocat'; Desc = 'simple lowercase' }
            @{ Name = 'Octocat'; Desc = 'mixed case' }
            @{ Name = 'my-org-123'; Desc = 'hyphens and numbers' }
            @{ Name = 'a'; Desc = 'single character' }
            @{ Name = 'ab'; Desc = 'two characters' }
            @{ Name = ('a' * 39); Desc = 'max length 39' }
        ) | ForEach-Object {
            It "Accepts valid owner: $($_.Desc)" {
                Test-GitHubNameValid -Name $_.Name -Type "Owner" | Should -Be $true
            }
        }
    }

    Context "Owner Validation - Invalid Cases" {
        @(
            @{ Name = '-invalid'; Desc = 'starts with hyphen' }
            @{ Name = 'invalid-'; Desc = 'ends with hyphen' }
            @{ Name = '--double'; Desc = 'starts with double hyphen' }
            @{ Name = ('a' * 40); Desc = 'exceeds 39 chars' }
            @{ Name = ''; Desc = 'empty string' }
            @{ Name = ' '; Desc = 'whitespace only' }
            @{ Name = 'has space'; Desc = 'contains space' }
            @{ Name = 'has.period'; Desc = 'contains period' }
            @{ Name = 'has_underscore'; Desc = 'contains underscore' }
        ) | ForEach-Object {
            It "Rejects invalid owner: $($_.Desc)" {
                Test-GitHubNameValid -Name $_.Name -Type "Owner" | Should -Be $false
            }
        }
    }

    Context "Owner Validation - Command Injection Payloads" {
        @(
            # Shell metacharacters
            @{ Name = 'owner; rm -rf /'; Desc = 'semicolon injection' }
            @{ Name = 'owner && whoami'; Desc = 'AND injection' }
            @{ Name = 'owner || id'; Desc = 'OR injection' }
            @{ Name = 'owner | cat /etc/passwd'; Desc = 'pipe injection' }
            @{ Name = 'owner$(whoami)'; Desc = 'command substitution $()' }
            @{ Name = 'owner`whoami`'; Desc = 'backtick injection' }
            @{ Name = "owner`ninjection"; Desc = 'newline injection' }
            @{ Name = "owner`rinjection"; Desc = 'carriage return injection' }
            @{ Name = 'owner > /tmp/pwned'; Desc = 'redirect injection' }
            @{ Name = 'owner < /etc/passwd'; Desc = 'input redirect' }

            # PowerShell specific
            @{ Name = 'owner;Start-Process calc'; Desc = 'PS semicolon' }
            @{ Name = '$(Write-Host pwned)'; Desc = 'PS subexpression' }
            @{ Name = '@{a="b"}.a'; Desc = 'PS hashtable access' }

            # URL/encoding attacks
            @{ Name = 'owner%00null'; Desc = 'null byte (URL encoded)' }
            @{ Name = 'owner%0Anewline'; Desc = 'newline (URL encoded)' }

            # Unicode homoglyphs (Cyrillic lookalikes)
            @{ Name = ([char]0x0430 + 'dmin'); Desc = 'Cyrillic "a" homoglyph' }
            @{ Name = ('o' + [char]0x0441 + 'tocat'); Desc = 'Cyrillic "c" homoglyph' }

            # Control characters
            @{ Name = "owner$([char]0)null"; Desc = 'embedded null' }
            @{ Name = "owner$([char]7)bell"; Desc = 'bell character' }
            @{ Name = "owner$([char]27)escape"; Desc = 'escape character' }
        ) | ForEach-Object {
            It "SECURITY: Rejects injection payload: $($_.Desc)" {
                Test-GitHubNameValid -Name $_.Name -Type "Owner" | Should -Be $false
            }
        }
    }

    Context "Repo Validation - Valid Cases" {
        @(
            @{ Name = 'my-repo'; Desc = 'with hyphen' }
            @{ Name = 'my_repo'; Desc = 'with underscore' }
            @{ Name = 'my.repo'; Desc = 'with period' }
            @{ Name = 'MyRepo123'; Desc = 'alphanumeric' }
            @{ Name = '.hidden'; Desc = 'starts with period' }
            @{ Name = ('a' * 100); Desc = 'max length 100' }
        ) | ForEach-Object {
            It "Accepts valid repo: $($_.Desc)" {
                Test-GitHubNameValid -Name $_.Name -Type "Repo" | Should -Be $true
            }
        }
    }

    Context "Repo Validation - Invalid Cases" {
        @(
            @{ Name = ('a' * 101); Desc = 'exceeds 100 chars' }
            @{ Name = ''; Desc = 'empty string' }
            @{ Name = ' repo'; Desc = 'leading space' }
            @{ Name = 'repo '; Desc = 'trailing space' }
            @{ Name = 'repo name'; Desc = 'contains space' }
        ) | ForEach-Object {
            It "Rejects invalid repo: $($_.Desc)" {
                Test-GitHubNameValid -Name $_.Name -Type "Repo" | Should -Be $false
            }
        }
    }
}
```

### 2.2 Complete Test Suite for `Test-SafeFilePath`

```powershell
Describe "Test-SafeFilePath - Security Boundary Tests" {

    BeforeAll {
        # Create test directory structure
        $script:TestRoot = Join-Path $TestDrive 'safe-root'
        $script:SubDir = Join-Path $script:TestRoot 'subdir'
        $script:OutsideDir = Join-Path $TestDrive 'outside'

        New-Item -Path $script:TestRoot -ItemType Directory -Force | Out-Null
        New-Item -Path $script:SubDir -ItemType Directory -Force | Out-Null
        New-Item -Path $script:OutsideDir -ItemType Directory -Force | Out-Null

        # Create test files
        'content' | Out-File (Join-Path $script:TestRoot 'valid.txt')
        'content' | Out-File (Join-Path $script:SubDir 'nested.txt')
        'content' | Out-File (Join-Path $script:OutsideDir 'outside.txt')
    }

    Context "Path Traversal - Unix Style" {
        @(
            '../../../etc/passwd'
            '../../etc/passwd'
            '../etc/passwd'
            'subdir/../../../etc/passwd'
            './subdir/../../../etc/passwd'
            'subdir/./../../etc/passwd'
        ) | ForEach-Object {
            It "SECURITY: Rejects Unix traversal: $_" {
                Test-SafeFilePath -Path $_ -AllowedBase $script:TestRoot | Should -Be $false
            }
        }
    }

    Context "Path Traversal - Windows Style" {
        @(
            '..\..\..\windows\system32'
            '..\..\windows\system32'
            '..\windows\system32'
            'subdir\..\..\..\windows\system32'
            '.\subdir\..\..\..\windows\system32'
            'subdir\.\..\..\windows\system32'
        ) | ForEach-Object {
            It "SECURITY: Rejects Windows traversal: $_" {
                Test-SafeFilePath -Path $_ -AllowedBase $script:TestRoot | Should -Be $false
            }
        }
    }

    Context "Path Traversal - Mixed/Encoded" {
        @(
            '..\/..\/etc/passwd'
            '..\/../windows/system32'
            '%2e%2e/%2e%2e/etc/passwd'
            '....//....//etc/passwd'
            '..;/etc/passwd'
            '../\../etc/passwd'
        ) | ForEach-Object {
            It "SECURITY: Rejects mixed/encoded traversal: $_" {
                Test-SafeFilePath -Path $_ -AllowedBase $script:TestRoot | Should -Be $false
            }
        }
    }

    Context "Null Byte Injection" {
        @(
            "valid.txt$([char]0)../etc/passwd"
            "valid$([char]0).txt"
        ) | ForEach-Object {
            It "SECURITY: Rejects null byte injection" {
                Test-SafeFilePath -Path $_ -AllowedBase $script:TestRoot | Should -Be $false
            }
        }
    }

    Context "Absolute Path Escapes" {
        It "SECURITY: Rejects absolute path outside base (Unix)" {
            Test-SafeFilePath -Path '/etc/passwd' -AllowedBase $script:TestRoot | Should -Be $false
        }

        It "SECURITY: Rejects absolute path outside base (Windows)" {
            Test-SafeFilePath -Path 'C:\Windows\System32\config\SAM' -AllowedBase $script:TestRoot | Should -Be $false
        }

        It "SECURITY: Rejects UNC paths" {
            Test-SafeFilePath -Path '\\server\share\file.txt' -AllowedBase $script:TestRoot | Should -Be $false
        }
    }

    Context "Valid Paths Within Base" {
        It "Accepts file in base directory" {
            $path = Join-Path $script:TestRoot 'valid.txt'
            Test-SafeFilePath -Path $path -AllowedBase $script:TestRoot | Should -Be $true
        }

        It "Accepts file in subdirectory" {
            $path = Join-Path $script:SubDir 'nested.txt'
            Test-SafeFilePath -Path $path -AllowedBase $script:TestRoot | Should -Be $true
        }

        It "Accepts relative path within base" {
            Push-Location $script:TestRoot
            try {
                Test-SafeFilePath -Path 'valid.txt' -AllowedBase $script:TestRoot | Should -Be $true
            }
            finally {
                Pop-Location
            }
        }
    }

    Context "Boundary Cases" {
        It "SECURITY: Rejects path that resolves outside base" {
            $outsidePath = Join-Path $script:OutsideDir 'outside.txt'
            Test-SafeFilePath -Path $outsidePath -AllowedBase $script:TestRoot | Should -Be $false
        }

        It "Handles base path as file (edge case)" {
            $filePath = Join-Path $script:TestRoot 'valid.txt'
            # If AllowedBase is a file, only that exact file should pass
            Test-SafeFilePath -Path $filePath -AllowedBase $filePath | Should -Be $true
        }
    }
}
```

### 2.3 Symlink Attack Tests

```powershell
Describe "Test-SafeFilePath - Symlink Security" -Skip:(-not $IsLinux -and -not $IsMacOS) {

    BeforeAll {
        $script:TestRoot = Join-Path $TestDrive 'symlink-test'
        $script:TargetDir = Join-Path $TestDrive 'target-outside'

        New-Item -Path $script:TestRoot -ItemType Directory -Force | Out-Null
        New-Item -Path $script:TargetDir -ItemType Directory -Force | Out-Null

        'secret' | Out-File (Join-Path $script:TargetDir 'secret.txt')

        # Create symlink inside TestRoot pointing outside
        $symlinkPath = Join-Path $script:TestRoot 'escape-link'
        New-Item -ItemType SymbolicLink -Path $symlinkPath -Target $script:TargetDir -ErrorAction SilentlyContinue
    }

    It "SECURITY: Detects symlink escape (requires symlink resolution)" {
        $maliciousPath = Join-Path $script:TestRoot 'escape-link' 'secret.txt'

        # Current implementation may not catch this - this test documents the gap
        # If this fails, symlink resolution needs to be added
        Test-SafeFilePath -Path $maliciousPath -AllowedBase $script:TestRoot | Should -Be $false
    }
}
```

**SECURITY GAP IDENTIFIED**: The current `Test-SafeFilePath` implementation uses `[System.IO.Path]::GetFullPath()` which does NOT resolve symlinks. An attacker could create a symlink inside the allowed base that points outside.

**Recommended Enhancement**:

```powershell
function Test-SafeFilePath {
    # ... existing params ...

    try {
        # Resolve symlinks for security
        $resolvedPath = if ($PSVersionTable.PSVersion.Major -ge 6) {
            # PowerShell Core: Use .NET Core's GetFinalPathName equivalent
            [System.IO.Path]::GetFullPath($Path)
            # Additional symlink resolution
            if (Test-Path $Path) {
                (Get-Item $Path -Force).Target ?? [System.IO.Path]::GetFullPath($Path)
            }
            else {
                [System.IO.Path]::GetFullPath($Path)
            }
        }
        else {
            [System.IO.Path]::GetFullPath($Path)
        }

        # Also resolve base for comparison
        $resolvedBase = [System.IO.Path]::GetFullPath($AllowedBase)

        # ... rest of comparison ...
    }
    catch {
        return $false
    }
}
```

---

## 3. Assert-ValidBodyFile Implementation (GAP-SEC-003)

### 3.1 AllowedBase Strategy

**Question**: What should `AllowedBase` be set to?

**Answer**: It depends on the trust boundary and use case.

| Context | AllowedBase | Reasoning |
|---------|-------------|-----------|
| GitHub Actions temp files | `$env:RUNNER_TEMP` | Workflow-created files only |
| Repository files | Repository root | Files checked into repo |
| User-provided paths | Current working directory | Restrict to working area |
| AI-generated content | Dedicated temp dir | Isolate AI output |

### 3.2 Implementation for Each Script

#### `Post-IssueComment.ps1` - BEFORE (Vulnerable)

```powershell
if ($BodyFile) {
    if (-not (Test-Path $BodyFile)) { Write-ErrorAndExit "Body file not found: $BodyFile" 2 }
    $Body = Get-Content -Path $BodyFile -Raw -Encoding UTF8
}
```

#### `Post-IssueComment.ps1` - AFTER (Secure)

```powershell
if ($BodyFile) {
    # Determine allowed base based on execution context
    $allowedBase = if ($env:RUNNER_TEMP) {
        # GitHub Actions context - allow temp and repo
        @($env:RUNNER_TEMP, $env:GITHUB_WORKSPACE) | Where-Object { $_ }
    }
    elseif ($env:GITHUB_WORKSPACE) {
        # CI context without temp
        $env:GITHUB_WORKSPACE
    }
    else {
        # Local execution - current directory
        (Get-Location).Path
    }

    # For multiple allowed bases, check each
    $isValid = $false
    foreach ($base in @($allowedBase)) {
        if (Test-SafeFilePath -Path $BodyFile -AllowedBase $base) {
            $isValid = $true
            break
        }
    }

    if (-not $isValid) {
        Write-ErrorAndExit "Body file path not in allowed location: $BodyFile" 1
    }

    if (-not (Test-Path $BodyFile)) {
        Write-ErrorAndExit "Body file not found: $BodyFile" 2
    }

    $Body = Get-Content -Path $BodyFile -Raw -Encoding UTF8
}
```

#### `Post-PRCommentReply.ps1` - Secure Implementation

```powershell
if ($BodyFile) {
    # Security: Validate file path before access
    $allowedBases = @(
        $env:RUNNER_TEMP
        $env:GITHUB_WORKSPACE
        (Get-Location).Path
    ) | Where-Object { $_ -and (Test-Path $_ -PathType Container) }

    $pathValid = $false
    foreach ($base in $allowedBases) {
        if (Test-SafeFilePath -Path $BodyFile -AllowedBase $base) {
            $pathValid = $true
            Write-Verbose "Body file validated against base: $base"
            break
        }
    }

    if (-not $pathValid) {
        Write-ErrorAndExit "SECURITY: Body file path outside allowed boundaries: $BodyFile" 1
    }

    if (-not (Test-Path $BodyFile -PathType Leaf)) {
        Write-ErrorAndExit "Body file not found or is directory: $BodyFile" 2
    }

    $Body = Get-Content -Path $BodyFile -Raw -Encoding UTF8
}
```

#### Workflow YAML - Secure File Handling

```yaml
- name: Post PRD Comment (PowerShell)
  shell: pwsh
  env:
    GH_TOKEN: ${{ github.token }}
    ISSUE_NUMBER: ${{ github.event.issue.number }}
    # Use runner temp for security isolation
    BODY_FILE: ${{ runner.temp }}/prd-comment-${{ github.run_id }}.md
  run: |
    # Validate environment
    $tempDir = $env:RUNNER_TEMP
    if (-not $tempDir -or -not (Test-Path $tempDir)) {
        Write-Error "RUNNER_TEMP not available"
        exit 1
    }

    # Generate unique filename
    $bodyFile = Join-Path $tempDir "prd-comment-$($env:GITHUB_RUN_ID).md"

    # Write content to isolated temp location
    $prdContent | Set-Content $bodyFile -Encoding UTF8

    # Use GitHub skill script with validated path
    & .claude/skills/github/scripts/issue/Post-IssueComment.ps1 `
      -Issue $env:ISSUE_NUMBER `
      -BodyFile $bodyFile `
      -Marker "AI-PRD-GENERATION"

    # Cleanup
    Remove-Item $bodyFile -ErrorAction SilentlyContinue
```

---

## 4. Token Security

### 4.1 Current State Analysis

The workflow uses multiple tokens:

| Token | Usage | Scope Risk |
|-------|-------|------------|
| `secrets.BOT_PAT` | Primary operations | Unknown scope - could be overprivileged |
| `github.token` | Fallback in some steps | Repository-scoped, minimal |
| `secrets.COPILOT_GITHUB_TOKEN` | Copilot CLI | Requires `copilot` scope |

### 4.2 Token Leakage Risks

**Risk 1: Token in Error Messages**

```bash
# VULNERABLE - token could appear in error output
gh api ... 2>&1 | tee output.log
```

**Risk 2: Token in Debug Output**

```bash
# VULNERABLE - diagnostics output shows token info
echo "GH_TOKEN: ${GH_TOKEN:+[SET - ${#GH_TOKEN} chars]}"
```

**Risk 3: Token in Uploaded Artifacts**

```yaml
# VULNERABLE if logs contain token errors
- uses: actions/upload-artifact@v4
  with:
    name: debug-logs
    path: /tmp/ai-review-*.txt
```

### 4.3 Token Security Recommendations

```yaml
# 1. Use minimum required token for each step
- name: Apply Labels
  env:
    # Use github.token (not BOT_PAT) for issue operations
    # github.token has repository-scoped permissions
    GH_TOKEN: ${{ github.token }}
  run: |
    # ...

# 2. Mask tokens in debug output
- name: Diagnose (Secure)
  run: |
    # Add to mask
    echo "::add-mask::$GH_TOKEN"
    # Now any output containing the token will be redacted

# 3. Never log token-related errors verbatim
- name: Safe Error Handling
  run: |
    if ! gh auth status 2>/dev/null; then
      echo "::error::GitHub authentication failed - check token configuration"
      # DON'T echo the actual error which might contain token info
      exit 1
    fi

# 4. Token scope validation
- name: Validate Token Scope
  run: |
    # Check required scopes before operations
    SCOPES=$(gh api -H "Authorization: token $GH_TOKEN" -i /user 2>/dev/null | grep -i x-oauth-scopes | cut -d: -f2)
    if ! echo "$SCOPES" | grep -q "repo"; then
      echo "::error::Token missing required 'repo' scope"
      exit 1
    fi
```

### 4.4 Token Scope Requirements

| Operation | Required Scope | Recommended Token |
|-----------|----------------|-------------------|
| Read issues | `repo` or `public_repo` | `github.token` |
| Edit issues/labels | `repo` | `github.token` |
| Post comments | `repo` | `github.token` |
| Copilot CLI | `copilot` | Dedicated `COPILOT_TOKEN` |

**Recommendation**: Use `github.token` for all GitHub API operations. Reserve `BOT_PAT` only for cross-repo operations that require it.

---

## 5. Threat Model: AI Review Workflow

### 5.1 Assets

| Asset | Sensitivity | Description |
|-------|-------------|-------------|
| Repository code | HIGH | Source code and configurations |
| GitHub tokens | CRITICAL | Authentication credentials |
| Issue/PR metadata | MEDIUM | Labels, milestones, assignments |
| AI model responses | MEDIUM | Could contain hallucinated malicious content |
| Workflow secrets | CRITICAL | All secrets in workflow context |

### 5.2 Threat Actors

| Actor | Capability | Motivation | Likelihood |
|-------|------------|------------|------------|
| Malicious issue author | LOW | Can craft malicious issue content | HIGH |
| Compromised AI model | MEDIUM | Could return malicious output | LOW |
| Supply chain attacker | HIGH | Compromise npm packages | MEDIUM |
| Insider threat | HIGH | Access to secrets | LOW |

### 5.3 Attack Surface

```
+-------------------+     +-----------------+     +------------------+
|  External Input   |---->|  AI Processing  |---->|  Shell Execution |
+-------------------+     +-----------------+     +------------------+
        |                        |                        |
        v                        v                        v
  Issue content            AI output               gh CLI commands
  PR descriptions          Labels                  File operations
  Comments                 Milestones              API calls
```

### 5.4 STRIDE Analysis

| Threat | Category | Attack Vector | Mitigation |
|--------|----------|---------------|------------|
| AI output injection | Spoofing | Malicious labels from AI | Input validation regex |
| Token theft | Tampering | Exfil via error messages | Token masking, minimal scopes |
| Workflow bypass | Repudiation | Silent failures hide attacks | Proper error handling |
| Data exfil | Information Disclosure | Secrets in logs | Never log secrets |
| Workflow DoS | Denial of Service | Long-running AI calls | Timeouts |
| Privilege escalation | Elevation | Overprivileged tokens | Minimal token scopes |

### 5.5 Additional Controls Needed

| Control | Priority | Implementation |
|---------|----------|----------------|
| AI output sanitization | P0 | Strict allowlist validation |
| Token scope reduction | P1 | Use `github.token` primarily |
| Audit logging | P1 | Log all security-relevant actions |
| Rate limiting awareness | P2 | Handle 429 responses gracefully |
| Supply chain verification | P2 | Pin npm packages with checksums |
| Secrets scanning | P2 | Ensure no secrets in output files |

---

## 6. Security Checklist for Implementation

### Pre-Implementation

- [ ] Review all input sources (issues, PRs, AI output)
- [ ] Identify all shell command executions
- [ ] Map token usage across all steps
- [ ] Document allowed file paths

### Implementation

- [ ] Apply strict regex validation to ALL AI output used in commands
- [ ] Replace `|| true` with proper error handling
- [ ] Add `Assert-ValidBodyFile` to all file-reading scripts
- [ ] Use `github.token` where `BOT_PAT` is not required
- [ ] Add token masking before any debug output

### Post-Implementation (PIV)

- [ ] Run security test suite (injection payloads)
- [ ] Verify no tokens appear in any logs
- [ ] Test path traversal attacks against file operations
- [ ] Validate error messages don't leak sensitive info
- [ ] Review workflow run logs for security issues

---

## 7. Recommended Plan Updates

### Update to Task 1.1 (Command Injection)

Replace the proposed regex `'^[\w\-\.\s]+$'` with:

```powershell
# Strict ASCII-only, no shell metacharacters, length-limited
$ValidLabelPattern = '^[a-zA-Z0-9](?:[a-zA-Z0-9 _\-\.]{0,48}[a-zA-Z0-9])?$|^[a-zA-Z0-9]$'
$DangerousChars = '[`$;|&<>(){}[\]''"\x00-\x1F\x7F-\xFF]'
```

### Update to Task 2.1-2.3 (Security Tests)

Add the comprehensive test suites from Section 2 of this report, including:
- Command injection payloads
- Path traversal variants
- Unicode homoglyph tests
- Symlink escape tests

### New Task: Token Security

Add a new task addressing:
- Token scope audit
- Token masking implementation
- Switch to `github.token` where possible

---

## Approval

| Role | Status | Date |
|------|--------|------|
| Security Agent | Completed | 2025-12-18 |

---

## References

- CWE-78: Improper Neutralization of Special Elements used in an OS Command
- CWE-22: Improper Limitation of a Pathname to a Restricted Directory
- CWE-200: Exposure of Sensitive Information
- GitHub Actions Security Hardening: https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions
