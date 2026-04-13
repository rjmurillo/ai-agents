# Security Assessment: Pre-commit QA Skip Options

**Date**: 2025-12-30
**Analyst**: Security Agent
**Input Document**: `.agents/analysis/pre-commit-qa-investigation-sessions-gap.md`
**Status**: Complete

---

## Executive Summary

This assessment evaluates security and compliance risks of four proposed options for allowing QA validation skip in investigation-only sessions. The current validator creates false positives that force `--no-verify` bypasses, which erodes the validation gate's integrity.

**Recommendation**: Option 2 (Explicit Investigation Mode) provides the best balance of security and usability. Option 1 introduces unacceptable complexity. Options 3 and 4 have narrower applicability or create overhead.

---

## Risk Matrix

| Option | Likelihood of Misuse | Impact if Misused | Risk Score | Verdict |
|--------|---------------------|-------------------|------------|---------|
| **Option 1**: Session-Level Detection | Low (0.2) | High (0.8) | 0.16 | [WARNING] Complexity risk |
| **Option 2**: Explicit Investigation Mode | Medium (0.4) | Low (0.3) | 0.12 | [PASS] Acceptable |
| **Option 3**: File-Based Exemption | Low (0.2) | Low (0.3) | 0.06 | [PASS] Limited scope |
| **Option 4**: QA Report Categories | Very Low (0.1) | Very Low (0.1) | 0.01 | [PASS] Overhead concern |

**Scoring**: Risk Score = Likelihood x Impact (scale 0-1)

---

## Option Analysis

### Option 1: Session-Level Change Detection

**Description**: Automatically detect what files the session changed vs. what the branch changed.

#### Security Assessment

| Factor | Rating | Justification |
|--------|--------|---------------|
| Attack Surface | High | Complex git history parsing introduces edge cases |
| Implementation Risk | High | Session boundary detection is fragile |
| Audit Trail | Medium | Automatic detection leaves implicit evidence |
| Bypass Potential | Medium | Edge cases could allow unintended QA skip |

**Vulnerabilities Identified**:

1. **CWE-391: Unchecked Error Condition** - Git history parsing can fail silently on rebases, force pushes, or amended commits
2. **Race Condition** - Multiple sessions on same branch could have overlapping commits, making session boundaries ambiguous
3. **False Negatives** - Agent could make code changes, discard them, but session still appears "investigation-only"

**Compliance Risk**: Medium

- Audit logs would show automatic determination, not explicit declaration
- Harder to prove intent during compliance audits
- Implicit decisions reduce accountability

**Recommendation**: [WARNING] Do not implement. Complexity introduces more risk than it solves.

---

### Option 2: Explicit Investigation Mode

**Description**: Allow sessions to self-declare as investigation-only with explicit evidence pattern (e.g., `SKIPPED: investigation-only`).

#### Security Assessment

| Factor | Rating | Justification |
|--------|--------|---------------|
| Attack Surface | Low | Simple pattern matching, no complex logic |
| Implementation Risk | Low | Follows existing `SKIPPED: docs-only` pattern |
| Audit Trail | High | Explicit declaration in session log |
| Bypass Potential | Medium | Misuse requires explicit false statement |

**Vulnerabilities Identified**:

1. **Trust-Based Control** - Agent could falsely claim investigation-only to skip QA
2. **CWE-284: Improper Access Control** - No technical enforcement of investigation-only claim

**Mitigations**:

| Mitigation | Effectiveness | Effort |
|------------|---------------|--------|
| Require session log have zero files in "Files changed" section | High | Low |
| CI validation cross-checks session commits vs claim | High | Medium |
| Pre-commit verifies staged files match claim | High | Low |

**Compliance Risk**: Low (with mitigations)

- Explicit declaration creates clear audit trail
- Matches existing docs-only pattern precedent
- Attestation model aligns with compliance frameworks (SOC2, ISO 27001)

**Recommendation**: [PASS] Implement with staged-file verification guardrail.

---

### Option 3: File-Based QA Exemption

**Description**: Allow sessions with only `.agents/sessions/*.md` changes to skip QA automatically.

#### Security Assessment

| Factor | Rating | Justification |
|--------|--------|---------------|
| Attack Surface | Low | File path matching is deterministic |
| Implementation Risk | Low | Simple path glob matching |
| Audit Trail | High | Based on actual staged files |
| Bypass Potential | Low | Can only skip QA when truly no code changes staged |

**Vulnerabilities Identified**:

1. **Narrow Scope** - Does not cover sessions that update memories (`.serena/memories/`)
2. **Inconsistency** - Session + memory update still requires QA (no actual code to QA)

**Compliance Risk**: Very Low

- Technical control based on file system state
- No human judgment required

**Recommendation**: [PASS] Acceptable but too narrow. Would not fully solve the problem.

---

### Option 4: QA Report Categories

**Description**: Expand QA evidence to include investigation reports as a category.

#### Security Assessment

| Factor | Rating | Justification |
|--------|--------|---------------|
| Attack Surface | Low | No change to validation logic |
| Implementation Risk | Low | Additive change only |
| Audit Trail | Very High | Every session has documented evidence |
| Bypass Potential | Very Low | Requires QA agent invocation |

**Vulnerabilities Identified**:

1. **Scope Creep** - QA agent may not be appropriate for pure investigation sessions
2. **Overhead** - Forces agent invocation when no action needed

**Compliance Risk**: Very Low

- Maximum documentation
- Clear evidence chain

**Recommendation**: [PASS] Secure but creates unnecessary overhead for common investigation patterns.

---

## Bypass Normalization Risk

**Critical Concern**: The analysis document identifies that agents currently bypass validation using `--no-verify`. This creates a normalization pattern where bypass becomes routine.

### Current State Risk

| Metric | Value |
|--------|-------|
| Bypass frequency | Unknown (not logged) |
| Detection capability | None |
| Accountability | None |

### Bypass Normalization Threat Model

| Threat | Likelihood | Impact | Mitigation |
|--------|------------|--------|------------|
| Agent learns `--no-verify` is acceptable | High | High | Provide legitimate skip path |
| Bypass used for actual code changes | Medium | Critical | Log all bypasses, CI post-validation |
| Bypass becomes undocumented norm | High | Medium | Track bypass rate in metrics |

**Recommendation**: Implement Option 2 primarily to **eliminate the bypass normalization risk**. A legitimate path prevents agents from learning that validation bypass is acceptable.

---

## Principle of Least Privilege

The session validation system should grant only the minimum permissions needed.

### Current State

- QA validation required for all sessions on code branches
- Only escape hatch is full `--no-verify` bypass (too permissive)

### Recommended State

- QA validation required for sessions with code/config changes
- Investigation-only sessions can skip with explicit attestation and verification
- `--no-verify` remains available but is logged and flagged

### Privilege Levels

| Level | Permissions | Who |
|-------|-------------|-----|
| Full validation | All checks enforced | Default for all sessions |
| Investigation skip | QA skipped with attestation | Sessions with no staged code changes |
| Full bypass | All checks skipped | Only with explicit human override |

---

## Recommended Guardrails

### Guardrail 1: Staged File Verification

```powershell
# In Validate-Session.ps1 QA skip logic
if ($Evidence -match 'SKIPPED:\s*investigation-only') {
    # Verify no code/config files staged
    $stagedFiles = @(git diff --cached --name-only)
    $codeFiles = $stagedFiles | Where-Object { $_ -notmatch '^\.agents/' }
    if ($codeFiles.Count -gt 0) {
        Fail 'E_INVESTIGATION_HAS_CODE' "Investigation skip claimed but staged files contain code: $($codeFiles -join ', ')"
    }
}
```

**Risk Reduced**: Prevents false investigation-only claims when code is staged.

### Guardrail 2: Session Log Files Changed Verification

```powershell
# Verify session log "Files changed" section is empty or contains only .agents/ paths
$filesChangedSection = Extract-FilesChangedSection $sessionText
if ($filesChangedSection -and ($filesChangedSection -notmatch '^\s*$')) {
    $nonAgentFiles = $filesChangedSection -split "`n" | Where-Object { $_ -notmatch '\.agents/' }
    if ($nonAgentFiles.Count -gt 0) {
        Fail 'E_INVESTIGATION_CLAIMS_FILES' "Investigation skip but Files changed section lists non-agent files."
    }
}
```

**Risk Reduced**: Detects inconsistency between claimed investigation-only and documented work.

### Guardrail 3: Bypass Logging

```powershell
# Log all --no-verify usage to .agents/validation/bypasses.log
if ($BypassDetected) {
    $entry = @{
        Timestamp = (Get-Date -Format 'o')
        SessionLog = $SessionLogPath
        Branch = $CurrentBranch
        User = $env:USER
    }
    $entry | ConvertTo-Json | Add-Content ".agents/validation/bypasses.log"
}
```

**Risk Reduced**: Creates audit trail for bypasses, enables trend analysis.

### Guardrail 4: CI Post-Validation

Add GitHub Actions workflow to:

1. Detect commits with session logs claiming investigation-only
2. Verify those commits contain only `.agents/` file changes
3. Flag violations in PR checks

**Risk Reduced**: Defense in depth. Pre-commit can be bypassed; CI cannot (without push access).

---

## Compliance Implications

### Audit Gap Analysis

| Scenario | Current | With Option 2 | Gap? |
|----------|---------|---------------|------|
| Code change without QA | Blocked | Blocked | No |
| Investigation without QA | Blocked (forces bypass) | Allowed with attestation | No |
| Investigation falsely claims code | Not detected | Detected by guardrails | No |
| Bypass used for code | Not detected | Logged, CI detectable | Improved |

### Compliance Framework Alignment

| Framework | Requirement | Option 2 Compliance |
|-----------|-------------|---------------------|
| SOC2 CC6.1 | Logical access controls | Attestation + verification |
| ISO 27001 A.12.6 | Technical vulnerability management | QA still required for code |
| NIST CSF PR.AC-4 | Access permissions managed | Least privilege enforced |

---

## Security Recommendation

### Preferred Option: Option 2 (Explicit Investigation Mode)

**Rationale**:

1. **Eliminates bypass normalization** - Provides legitimate path, reducing `--no-verify` usage
2. **Maintains accountability** - Explicit attestation creates audit trail
3. **Low implementation risk** - Follows existing `docs-only` pattern
4. **Supports guardrails** - Can add technical verification without architecture change
5. **Complies with least privilege** - Grants only needed exemption, not full bypass

### Required Guardrails for Approval

| Guardrail | Priority | Status |
|-----------|----------|--------|
| Staged file verification (no code staged) | P0 - Required | Pending implementation |
| Session log consistency check | P1 - Recommended | Pending implementation |
| Bypass logging | P1 - Recommended | Pending implementation |
| CI post-validation | P2 - Optional | Future enhancement |

### Implementation Constraints

1. MUST NOT allow investigation skip when any non-`.agents/` files are staged
2. MUST require explicit `SKIPPED: investigation-only` evidence (not implicit)
3. SHOULD log all skip decisions for audit purposes
4. SHOULD implement CI validation as defense-in-depth

---

## Conclusion

The current QA validation gap creates a security anti-pattern where agents learn to bypass validation entirely. Implementing Option 2 with the specified guardrails:

- Reduces bypass normalization risk (High impact)
- Maintains audit trail (Compliance requirement)
- Adds defense-in-depth through layered verification
- Aligns with principle of least privilege

**Verdict**: [PASS] Option 2 recommended with P0 guardrail as mandatory condition.

---

## References

- Analysis Document: `.agents/analysis/pre-commit-qa-investigation-sessions-gap.md`
- Session Protocol: `.agents/SESSION-PROTOCOL.md`
- Validation Script: `scripts/Validate-Session.ps1`
- Security Validation Chain Memory: `security-validation-chain`
- QA Routing Memory: `quality-qa-routing`
