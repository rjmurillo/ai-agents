# Plan Critique: Investigation-Only Session QA Exemption

**Date**: 2025-12-30
**Critic**: Critic Agent
**Reviewed Documents**:
- `.agents/analysis/investigation-session-patterns-analyst-report.md`
- `.agents/architecture/ASSESSMENT-session-qa-validation-options.md`
- `.agents/security/SA-pre-commit-qa-skip-options.md`

---

## Verdict

**[NEEDS REVISION]**

---

## Summary

All three specialist agents (analyst, architect, security) converge on **Option 2: Explicit Investigation Mode** as the recommended solution. The proposal has strong technical merit and addresses a real pain point (29.4% of sessions require workarounds). However, critical implementation gaps and edge cases require resolution before implementation can proceed.

**Strengths**: Clear consensus, evidence-based analysis, practical guardrails proposed.

**Critical Gaps**: Undefined staged-file guardrail behavior, missing edge case handling, incomplete protocol documentation requirements.

---

## Strengths

- **Unanimous agreement**: All three agents independently recommend Option 2
- **Evidence-based**: Analyst quantified the problem (72/245 sessions, 29.4%)
- **Practical guardrails**: Security agent proposes staged-file verification as P0 requirement
- **Pattern consistency**: Architect confirms alignment with existing `SKIPPED: docs-only` pattern
- **Risk mitigation**: Security assessment shows acceptable risk with guardrails (0.12 risk score)

---

## Issues Found

### Critical (Must Fix)

- [ ] **Undefined Guardrail Logic for `.agents/` Files** (Location: All reports, Line: Security 209-214, Architect 96-104)

  **Issue**: Security agent's Guardrail 1 excludes files matching `'^\.agents/'` from code file detection. This means sessions that ONLY update `.agents/sessions/` and `.serena/memories/` would pass the staged-file check and be allowed to use investigation-only skip. However, the logic is inconsistent:

  - Security report (Line 210): `$codeFiles = $stagedFiles | Where-Object { $_ -notmatch '^\.agents/' }`
  - Implication: ANY file under `.agents/` is exempt, including `.agents/planning/`, `.agents/architecture/ADR-*.md`, `.agents/qa/`, etc.

  **Problem**: This is too permissive. A session that creates a new ADR (`.agents/architecture/ADR-008.md`) or updates a planning document (`.agents/planning/PRD-feature.md`) could claim investigation-only skip even though it produced implementation artifacts.

  **Expected Behavior**: Only specific `.agents/` subdirectories should be exempt:
  - `.agents/sessions/` (session logs)
  - `.agents/analysis/` (investigation outputs)
  - `.serena/memories/` (cross-session context)

  **NOT exempt**:
  - `.agents/planning/` (implementation plans)
  - `.agents/architecture/` (ADRs are design decisions)
  - `.agents/qa/` (QA reports)
  - `.agents/critique/` (plan reviews)

  **Required Fix**: Define explicit allowlist of investigation-only artifact paths.

---

- [ ] **Missing Edge Case: Session Log + Code Change Scenario** (Location: All reports, implicit)

  **Issue**: All three reports assume investigation sessions will ONLY have `.agents/sessions/*.md` and `.serena/memories/*.md` staged. None address the scenario where an agent:

  1. Starts investigation session
  2. Discovers a one-line bug fix needed
  3. Makes the fix
  4. Attempts to commit with "investigation-only" claim

  **Current Proposed Logic**: Would FAIL the staged-file check (code file detected).

  **Failure Mode**: Agent receives error: "Investigation skip claimed but staged files contain code"

  **Recovery Path**: Unclear. Must agent:
  - Split into two commits (investigation artifacts, then code separately)?
  - Change session mode from investigation to implementation?
  - Invoke QA after all?

  **Required Fix**: Document the recovery path for investigation sessions that discover code changes are needed.

---

- [ ] **Inconsistent Evidence Pattern Specification** (Location: Architect 96, Security 207, Analyst 203)

  **Issue**: All three reports reference `SKIPPED: investigation-only` as the evidence pattern, but:

  - Analyst (Line 203): `'(?i)SKIPPED:\s*investigation-only'` (case-insensitive)
  - Security (Line 207): `'SKIPPED:\s*investigation-only'` (case-sensitive implied)
  - Architect (Line 96): `investigation-only evidence` (no exact pattern)

  **Problem**: Validator regex must match session log entry exactly. Case sensitivity matters.

  **Required Fix**: Specify exact regex pattern with case sensitivity decision documented.

---

### Important (Should Fix)

- [ ] **No Specification for "No Code Files Staged" Definition** (Location: Security 209-214)

  **Issue**: Security guardrail checks `$_ -notmatch '^\.agents/'` but does not define what constitutes a "code file."

  **Questions**:
  - Is `.github/workflows/*.yml` a code file? (Yes - workflow logic)
  - Is `package.json` a code file? (Yes - dependency config)
  - Is `.gitignore` a code file? (Debatable)
  - Is `README.md` a code file? (No - but is it docs-only?)

  **Current Validator Logic**: Uses `Is-DocsOnly()` function (Line 306-309) which checks file extensions.

  **Recommendation**: Reuse existing `Is-DocsOnly()` logic or define explicit code file extensions list.

---

- [ ] **Memory Update Pattern Not Addressed** (Location: All reports, implicit)

  **Issue**: Analyst report (Line 222) mentions sessions updating `.serena/memories/` as investigation outputs. None of the reports specify whether memory-only updates should use investigation-only skip.

  **Scenario**: Agent reads codebase, updates memory with learnings, creates session log. No code changes. Should this use investigation-only skip?

  **Current Proposed Logic**: Would PASS staged-file check (no code files) → allowed to skip QA.

  **Question**: Is this intended behavior or should memory updates require different handling?

  **Recommendation**: Explicitly document memory-update-only sessions as valid investigation sessions.

---

- [ ] **CI Backstop Implementation Details Missing** (Location: Analyst 199, Security 252-259)

  **Issue**: Both analyst and security recommend CI validation as defense-in-depth, but no implementation specification provided.

  **Required for Implementation**:
  1. Which workflow triggers? (on push? on PR?)
  2. What constitutes a violation? (investigation claim + code files in commit diff?)
  3. What action on violation? (fail check? comment on PR?)
  4. How to handle multi-commit sessions? (check each commit individually?)

  **Recommendation**: Defer CI backstop to Phase 2 (post-implementation enhancement). Mark as P2 in all reports.

---

### Minor (Consider)

- [ ] **Bypass Logging Not Specified in Implementation Plan** (Location: Security 236-249)

  **Issue**: Security recommends logging all `--no-verify` bypasses to `.agents/validation/bypasses.log` but no implementation owner specified.

  **Question**: Is bypass logging in scope for this proposal or separate work item?

  **Recommendation**: Clarify if bypass logging is P0 requirement for investigation-only implementation or separate P1 task.

---

- [ ] **Pattern Proliferation Concern Unresolved** (Location: Architect 127-134)

  **Issue**: Architect flags risk of `SKIPPED:` pattern proliferation (investigation-only, docs-only, what's next?).

  **Proposed Mitigation**: "Create enum/constant for valid skip reasons. Validate against known list."

  **Status**: Mitigation proposed but not included in implementation plan.

  **Recommendation**: Add to implementation checklist: "Define skip-reason enum and validate against it."

---

## Questions for Planner

1. **Staged-File Allowlist Scope**: What `.agents/` subdirectories should be considered investigation-only artifacts vs implementation artifacts? Recommend explicit allowlist.

2. **Mixed Session Handling**: If an investigation session discovers a code change is needed, what is the recovery path? Split commits? Change session mode? Document the workflow.

3. **Case Sensitivity**: Should `SKIPPED: investigation-only` be case-insensitive like existing patterns? What is the exact regex validator should use?

4. **Memory Updates**: Are memory-only updates (`.serena/memories/*.md`) considered investigation sessions or do they require special handling?

5. **CI Backstop Priority**: Is CI validation P0 (required for initial implementation) or P2 (future enhancement)? Security marks it P2; analyst marks it P1.

---

## Recommendations

### Implementation Priority Changes

| Item | Current | Recommended | Rationale |
|------|---------|-------------|-----------|
| CI backstop validation | P1 (analyst) / P2 (security) | P2 | Pre-commit guardrail sufficient; CI is defense-in-depth |
| Bypass logging | P1 (security) | P1 (separate task) | Out of scope for investigation-only feature |
| Session log consistency check | P1 (security) | P0 | Critical for detecting false claims |

### Proposed Staged-File Allowlist

```powershell
# Investigation-only sessions may ONLY stage these paths:
$investigationPaths = @(
    '^\.agents/sessions/',      # Session logs
    '^\.agents/analysis/',      # Investigation outputs
    '^\.agents/retrospective/', # Learnings
    '^\.serena/memories/',      # Cross-session context
    '^\.agents/critique/'       # Plan reviews (critic sessions are investigation)
)

# All other paths are considered implementation artifacts or code
```

**Rationale**: Explicitly defines investigation artifacts vs implementation artifacts. Prevents abuse while supporting legitimate investigation work.

### Proposed Evidence Pattern

```powershell
# Case-insensitive to match existing docs-only pattern
if ($row.Evidence -match '(?i)SKIPPED:\s*investigation-only') {
  # Investigation skip logic
}
```

**Rationale**: Consistency with existing `(?i)SKIPPED:\s*docs-only` pattern (Line 348 of Validate-Session.ps1).

---

## Internal Consistency Check

### Agent Agreement Analysis

| Topic | Analyst | Architect | Security | Consensus? |
|-------|---------|-----------|----------|------------|
| Recommended Option | Option 2 | Option 2 | Option 2 | [PASS] |
| Staged-file guardrail required | Yes (Line 198) | Yes (Line 90) | Yes (P0, Line 300) | [PASS] |
| CI backstop priority | P1 (Line 200) | Not specified | P2 (Line 302) | [FAIL] Priority conflict |
| Session log consistency check | Recommended (Line 198) | Not specified | P1 (Line 301) | [WARNING] Gap |
| Bypass logging | Not specified | Not specified | P1 (Line 301) | [WARNING] Out of scope? |

**Conflict Resolution Required**: CI backstop priority (P1 vs P2).

**Recommendation**: Adopt P2 for CI backstop. Pre-commit staged-file check is sufficient enforcement. CI validation adds defense-in-depth but is not blocking for initial implementation.

---

### Cross-Domain Risk Assessment

| Risk Type | Analyst Finding | Architect Finding | Security Finding | Aligned? |
|-----------|----------------|-------------------|------------------|----------|
| Bypass normalization | High (Line 159) | Not assessed | High (Line 154) | [PASS] |
| Implementation complexity | Low (Option 2) | Low (Option 2) | Low (Option 2) | [PASS] |
| False positives | Medium (trust-based) | Medium (Line 60) | Medium (Line 77) | [PASS] |
| Audit trail | High value (Line 165) | High value (Line 111) | High value (Line 72) | [PASS] |

**Unanimous Agreement**: Option 2 provides acceptable risk with guardrails.

---

## Ergonomic Concerns for Agent Usability

### Concern 1: Error Message Clarity

**Scenario**: Agent attempts investigation-only skip but has `.agents/planning/PRD-feature.md` staged.

**Current Proposed Error** (Security Line 212): "Investigation skip claimed but staged files contain code: .agents/planning/PRD-feature.md"

**Issue**: Error message says "code" but `.md` files are not code. Confusing.

**Recommendation**: Improve error message:

```text
Investigation skip claimed but staged files contain implementation artifacts (not investigation outputs): .agents/planning/PRD-feature.md

Investigation sessions may only stage:
  - .agents/sessions/ (session logs)
  - .agents/analysis/ (investigation outputs)
  - .serena/memories/ (memory updates)

Current staged files include implementation artifacts, which require QA validation.
```

### Concern 2: Discovery Path for New Agents

**Issue**: New agents must learn about investigation-only mode. How do they discover it?

**Current State**: SESSION-PROTOCOL.md mentions docs-only skip (Line 266) but investigation-only is not yet documented.

**Recommendation**: Add to SESSION-PROTOCOL.md Phase 2.5 section:

```markdown
4. The agent MAY skip QA validation when:
   a. All modified files are documentation files (editorial changes only) → Use "SKIPPED: docs-only"
   b. Session is investigation-only (no code/config changes) → Use "SKIPPED: investigation-only"
```

### Concern 3: Mid-Session Mode Changes

**Issue**: Agent starts investigation session, discovers code change needed. What happens?

**Current Proposal**: No recovery path documented.

**Recommendation**: Add to SESSION-PROTOCOL.md:

```markdown
**Investigation Session Mode Change**: If an investigation session discovers code changes are needed:
1. Complete investigation artifacts (analysis docs, session log)
2. Commit investigation work with "SKIPPED: investigation-only"
3. Start NEW session for code changes (with QA validation)
4. Reference investigation session in implementation session log
```

**Rationale**: Clear separation of investigation vs implementation work. Prevents mixed sessions that are hard to validate.

---

## Edge Cases Not Addressed

### Edge Case 1: Concurrent Sessions on Same Branch

**Scenario**: Two agents working on different aspects of the same feature branch.
- Agent A: Investigation session (reading code, updating memory)
- Agent B: Implementation session (writing code)

**Problem**: Agent A's commit might happen while Agent B's code changes are on the branch (not yet committed).

**Validator Behavior**: Uses `git diff $startingCommit..HEAD` (Line 300), so validator sees Agent B's uncommitted changes in branch diff.

**Result**: Agent A investigation session blocked by QA requirement (even though Agent A made no code changes).

**Current Proposal**: Does not address this edge case.

**Mitigation**: Staged-file check is immune to this issue (only checks what Agent A staged, not branch state).

**Verdict**: [PASS] Staged-file guardrail resolves this edge case.

---

### Edge Case 2: Amended Commits

**Scenario**: Agent creates investigation-only commit, then amends it to add forgotten session log section.

**Problem**: `git commit --amend` re-triggers pre-commit hook.

**Validator Behavior**: Re-checks session log, evidence pattern still matches.

**Result**: Should pass (idempotent validation).

**Verdict**: [PASS] No special handling needed.

---

### Edge Case 3: Session Log Created After Code Changes

**Scenario**: Agent makes code changes, then creates session log retrospectively, claims investigation-only.

**Validator Behavior**: Staged-file check includes code files → FAIL.

**Result**: Blocked correctly.

**Verdict**: [PASS] Guardrail prevents retroactive false claims.

---

### Edge Case 4: Empty Staged Files

**Scenario**: Agent runs validator on commit with no staged files (e.g., testing pre-commit hook).

**Proposed Logic** (Security Line 209): `$stagedFiles = @(git diff --cached --name-only)`

**Result**: `$stagedFiles` is empty array → `$codeFiles` is empty → passes staged-file check.

**Problem**: Session log might claim investigation-only but no actual commit occurs.

**Is This a Problem?**: No commit means no persistence, so no validation needed.

**Verdict**: [PASS] No issue.

---

## Staged-File Guardrail Sufficiency Assessment

### Guardrail Logic (Security Proposal)

```powershell
if ($Evidence -match 'SKIPPED:\s*investigation-only') {
    $stagedFiles = @(git diff --cached --name-only)
    $codeFiles = $stagedFiles | Where-Object { $_ -notmatch '^\.agents/' }
    if ($codeFiles.Count -gt 0) {
        Fail 'E_INVESTIGATION_HAS_CODE' "Investigation skip claimed but staged files contain code: $($codeFiles -join ', ')"
    }
}
```

### Sufficiency Analysis

| Attack Vector | Guardrail Defense | Sufficient? |
|---------------|-------------------|-------------|
| Claim investigation-only with code staged | Staged-file check detects code → FAIL | [PASS] |
| Claim investigation-only, unstage code before commit | Only investigation artifacts committed → PASS (legitimate) | [PASS] |
| Stage `.agents/planning/PRD.md`, claim investigation | Current logic: PASS (`.agents/` exempt) | [FAIL] Too permissive |
| Stage `.github/workflows/ci.yml`, claim investigation | Detected as code → FAIL | [PASS] |
| Use `--no-verify` to bypass entirely | Not prevented by this guardrail | [N/A] Out of scope |

**Verdict**: Guardrail is MOSTLY sufficient but requires **allowlist refinement** (Critical Issue 1).

---

## Approval Conditions

Implementation may proceed ONLY after resolving:

### Blocking Issues (Must Fix Before Implementation)

1. **Define Investigation Artifact Allowlist** (Critical Issue 1)
   - Specify exactly which `.agents/` paths are investigation-only
   - Update guardrail logic to use allowlist instead of blanket `.agents/` exemption

2. **Specify Exact Evidence Pattern Regex** (Critical Issue 3)
   - Document case sensitivity decision
   - Provide exact regex string for validator

3. **Document Mixed Session Recovery Path** (Critical Issue 2)
   - Update SESSION-PROTOCOL.md with workflow for investigation sessions that discover code changes
   - Specify: split into two commits or change session mode?

### Recommended Additions (Should Address)

4. **Clarify Memory-Update Sessions** (Important Issue 2)
   - Explicitly state whether memory-only updates use investigation-only skip

5. **Add Session Log Consistency Check** (Important Issue 2, Security P1)
   - Validate session log "Files changed" section matches staged files

6. **Resolve CI Backstop Priority** (Important Issue 3, Agent Conflict)
   - Analyst: P1, Security: P2 → Recommend P2 for initial implementation

---

## Proposed Implementation Sequence

Once blocking issues resolved:

### Phase 1: Validator Update (P0)

1. Define investigation artifact allowlist constant
2. Add `SKIPPED: investigation-only` evidence pattern (case-insensitive)
3. Implement staged-file guardrail with allowlist check
4. Add session log consistency verification
5. Unit test all validation paths

### Phase 2: Documentation (P0)

1. Update SESSION-PROTOCOL.md Phase 2.5 with investigation-only conditions
2. Add mixed-session recovery workflow
3. Document memory-update sessions
4. Update session log template with investigation-only example

### Phase 3: Defense-in-Depth (P1-P2)

1. (P1) Create skill "Check QA skip eligibility" for agent self-service
2. (P2) Implement CI backstop validation
3. (P2) Add bypass logging (separate task)

---

## Impact Analysis Review

All three agents completed their domain analysis:

**Consultation Coverage**: 3/3 specialists consulted (analyst, architect, security)

**Cross-Domain Conflicts**: None - unanimous recommendation for Option 2

**Escalation Required**: No - agents agree on approach

### Specialist Agreement Status

| Specialist | Agrees with Plan | Concerns |
|------------|-----------------|----------|
| Analyst | Yes | None - quantified problem and validated solution |
| Architect | Yes | Pattern proliferation (mitigation proposed) |
| Security | Yes | Trust-based element (guardrails mitigate) |

**Unanimous Agreement**: Yes

---

## Conclusion

The proposal has strong technical merit and addresses a real friction point in the session protocol. All three specialist agents independently converged on Option 2 (Explicit Investigation Mode) with staged-file guardrails.

**However**, critical implementation details require clarification before implementation can proceed:

1. Investigation artifact allowlist must be explicitly defined (not blanket `.agents/` exemption)
2. Evidence pattern regex must be specified exactly
3. Mixed-session recovery path must be documented

**Once these blocking issues are resolved**, the proposal is ready for implementation with high confidence of success.

**Estimated Effort** (post-revision):
- Validator implementation: 3-4 hours
- Documentation updates: 1-2 hours
- Testing: 2-3 hours
- **Total**: 6-9 hours

**Risk Assessment**: Low (with guardrails), Medium (without allowlist refinement)

---

## Recommended Next Steps

1. **Immediate**: Return to planner to resolve blocking issues (allowlist definition, evidence pattern, recovery path)
2. **After revision**: Route to implementer for validator and documentation updates
3. **Post-implementation**: Route to qa for validation of new logic paths
4. **Future**: Consider P2 enhancements (CI backstop, bypass logging)

---

## Files Referenced

- `.agents/analysis/investigation-session-patterns-analyst-report.md`
- `.agents/architecture/ASSESSMENT-session-qa-validation-options.md`
- `.agents/security/SA-pre-commit-qa-skip-options.md`
- `.agents/SESSION-PROTOCOL.md` (Lines 252-274)
- `scripts/Validate-Session.ps1` (Lines 336-351, 296-309)
