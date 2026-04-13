# Architectural Assessment: Session QA Validation Options

**Date**: 2025-12-30
**Author**: Architect Agent
**Status**: Complete

## Summary

The pre-commit session validator requires QA reports for ALL sessions on branches with code changes, regardless of whether the individual session made code changes. This creates friction for investigation-only sessions.

## Design Intent Alignment Analysis

### SESSION-PROTOCOL.md Design Intent

The protocol establishes a **verification-based enforcement** model with these key principles:

1. **Observable checkpoints that produce verifiable evidence** (Section: Protocol Enforcement Model)
2. **QA validation after feature implementation** (Phase 2.5: "MUST route to qa agent after completing feature implementation")
3. **Skip condition explicitly scoped**: "MAY skip QA validation only when all modified files are documentation files"

### Current Implementation Gap

| Protocol Intent | Validator Implementation | Alignment |
|----------------|------------------------|-----------|
| "after feature implementation" | After any code on branch | [FAIL] Overreach |
| "all modified files are documentation" | Branch-level diff, not session-level | [FAIL] Wrong scope |
| "verification-based enforcement" | Evidence pattern matching | [PASS] Correct mechanism |

**Root Cause**: The validator uses `git diff $startingCommit..HEAD` which captures all branch changes, not session changes. An investigation session on a branch with prior code changes inherits QA requirements from work it did not perform.

## Option Evaluation Matrix

| Criterion | Option 1: Session-Level Detection | Option 2: Investigation Mode | Option 3: File-Based Exemption | Option 4: QA Categories |
|-----------|----------------------------------|------------------------------|-------------------------------|------------------------|
| **Separation of Concerns** | High - git handles change detection | Medium - session self-declares | Medium - staged files determine | Low - QA scope creep |
| **Maintainability** | Low - complex git boundary tracking | High - single regex pattern | Medium - additional logic | Medium - new report type |
| **Pattern Fit** | Low - no precedent in codebase | High - matches `SKIPPED: docs-only` | Medium - similar to docsOnly | Low - QA agent repurposing |
| **Verification Strength** | High - automated, objective | Medium - trust-based with evidence | High - automated, objective | Medium - requires new validation |
| **Implementation Effort** | High - session boundary detection | Low - add evidence pattern | Low - modify staged file check | Medium - new QA category |
| **Risk of Misuse** | Low - technical enforcement | Medium - could skip QA improperly | Low - technical enforcement | Medium - category ambiguity |

### Option Analysis

**Option 1: Session-Level Change Detection**

Architecturally sound but violates the simplicity principle. Git does not natively track "session boundaries" since multiple commits may occur within a session. Would require:

- Tracking first/last commit of session
- Comparing session-level diff vs branch-level diff
- Complex edge cases for rebases, merges, amendments

**Verdict**: Overengineered. Reject.

**Option 2: Explicit Investigation Mode**

Aligns with existing `SKIPPED: docs-only` pattern. Adds `SKIPPED: investigation-only` evidence marker. Maintains verification-based enforcement through:

- Explicit declaration in session log
- Pattern matching in validator
- Audit trail of investigation intent

**Concern**: Trust-based element. Agents could claim investigation mode to skip QA. Mitigation: CI workflow can cross-check if staged files include code changes (mismatch would be flagged).

**Verdict**: Recommended with mitigation.

**Option 3: File-Based QA Exemption**

Checks staged files at commit time rather than branch history. If staged files are only `.agents/sessions/*.md` and `.serena/memories/*.md`, skip QA requirement.

**Concern**: Too narrow. Sessions that update memories plus session logs still represent investigation work but would require QA under this model if the memory contains non-markdown. Also, pattern requires careful crafting to avoid exempting actual code commits.

**Verdict**: Viable but inflexible.

**Option 4: QA Report Categories**

Expands QA agent to produce "investigation report" instead of "validation report". All sessions have evidence artifacts.

**Concern**: Violates single responsibility. QA agent validates code quality; research documentation is analyst agent's domain. Creates overhead for simple investigations.

**Verdict**: Scope creep. Reject.

## Architectural Recommendation

**Recommended Option**: Option 2 (Explicit Investigation Mode) with Option 3 as secondary verification.

### Implementation Approach

1. **Add `SKIPPED: investigation-only` evidence pattern** to validator (matches existing pattern structure)
2. **Require no code files in staged changes** when using investigation mode (prevents misuse)
3. **Document in SESSION-PROTOCOL.md** the conditions for investigation mode

### Proposed Validation Logic

```text
if ($isQaRow) {
  if (investigation-only evidence AND no code files staged) {
    # Valid investigation skip
  } elseif (docs-only evidence AND only .md files on branch) {
    # Valid docs-only skip
  } else {
    # Require QA report
  }
}
```

### Rationale

1. **Separation of concerns**: Validator handles commit validation; session author declares intent; git provides staged file list
2. **Least change principle**: Extends existing `SKIPPED:` pattern rather than introducing new mechanism
3. **Testability**: Clear conditions that can be unit tested
4. **Audit trail**: Investigation mode explicitly documented in session log
5. **Defense in depth**: Dual check (declaration + staged files) prevents gaming

## Architectural Concerns

### Concern 1: Session vs Branch Scope Mismatch

The fundamental issue is that the validator operates at commit time but checks branch-level history. A clean fix would involve:

- Recording session boundaries in git notes, or
- Using staged files exclusively instead of branch history

**Impact**: Technical debt in current approach.

**Mitigation**: Option 2 sidesteps this by shifting responsibility to session author with verification guard.

### Concern 2: Pattern Proliferation

Adding `SKIPPED: investigation-only` joins `SKIPPED: docs-only`. Future exemption types could proliferate.

**Impact**: Validator complexity grows.

**Mitigation**: Create enum/constant for valid skip reasons. Validate against known list.

### Concern 3: QA Agent Responsibility Boundary

Current model: QA agent validates code. Investigation sessions have no code to validate. This is a legitimate exemption, not a bypass.

**Impact**: None if implementation is correct.

**Confirmation**: SESSION-PROTOCOL.md says "after feature implementation" not "after every session."

## Dependencies

1. `Validate-Session.ps1` modification (lines 336-351)
2. `SESSION-PROTOCOL.md` documentation update
3. Session log template update (if investigation mode requires specific sections)

## Architectural Decision Required

This assessment supports creating an ADR if the team decides to implement Option 2. The decision involves:

- Accepting trust-based element with technical mitigation
- Extending validation patterns
- Updating protocol documentation

**Recommendation**: Proceed with Option 2 implementation. The design aligns with protocol intent ("after feature implementation"), maintains verification-based enforcement (dual check), and follows existing patterns (`SKIPPED:` prefix).

## Evidence Summary

| Source | Key Finding |
|--------|-------------|
| SESSION-PROTOCOL.md:252-274 | QA "after feature implementation" - investigation sessions exempt by intent |
| Validate-Session.ps1:296-304 | Branch-level diff creates overreach |
| Validate-Session.ps1:345-348 | `SKIPPED: docs-only` pattern establishes precedent |
| Analysis document | Session 106 case study demonstrates real-world friction |
