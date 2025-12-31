---
status: accepted
date: 2025-12-30
decision-makers:
  - orchestrator
consulted:
  - analyst
  - architect
  - security
  - critic
  - independent-thinker
  - high-level-advisor
informed: []
---

# ADR-034: Investigation Session QA Exemption

## Status

Accepted

## Date

2025-12-30

## Context

The session protocol pre-commit validator requires QA validation for ALL sessions on branches with code changes, regardless of whether the individual session made any code changes. This creates a usability gap for investigation-only sessions.

### Problem Statement

The validator determines `$docsOnly` from branch-level `git diff`, not from the session's actual work. An investigation session (read-only analysis, CI debugging, research) on a branch with code changes is forced to:

1. Provide a QA report (nothing to QA), or
2. Use `--no-verify` bypass (undermines validation)

### Evidence

| Source | Finding |
|--------|---------|
| Analyst Report | 72/245 sessions (29.4%) are investigation-only |
| Session 106 | Investigation session blocked by QA requirement; required `--no-verify` bypass |
| Session Protocol | No provision for investigation-only sessions |

**Session 106 Reference**: `.agents/sessions/2025-12-30-session-106-pr-593-ci-fix.md`

### Multi-Agent Review

Six specialist agents reviewed this ADR and converged on Option 2 (Explicit Investigation Mode):

| Agent | Recommendation | Key Finding |
|-------|---------------|-------------|
| Analyst | Option 2 | 29.4% sessions affected; highest frequency gap |
| Architect | Option 2 | Aligns with existing `SKIPPED: docs-only` pattern |
| Security | Option 2 | Risk score 0.12 with guardrails (acceptable) |
| Critic | Option 2 (after revision) | Identified 3 blocking issues, all addressable |
| Independent Thinker | Option 2 | Validated with contrarian analysis |
| High-Level Advisor | Option 2 | Strategic alignment confirmed |

## Decision

Add investigation-only session exemption to pre-commit QA validation with staged-file guardrails.

### Evidence Pattern

```powershell
# Case-insensitive to match existing docs-only pattern
if ($row.Evidence -match '(?i)SKIPPED:\s*investigation-only') {
    # Investigation skip logic
}
```

### Investigation Artifact Allowlist

Sessions claiming `SKIPPED: investigation-only` may ONLY have these paths staged:

```powershell
$investigationAllowlist = @(
    '^\.agents/sessions/',        # Session logs
    '^\.agents/analysis/',        # Investigation outputs
    '^\.agents/retrospective/',   # Learnings
    '^\.serena/memories($|/)',    # Cross-session context (matches file or subdirs)
    '^\.agents/security/'         # Security assessments
)
```

**Allowlist Owner**: Architect agent (reviews additions via ADR amendment)

**Not Allowed** (require QA validation):

| Path Pattern | Rationale |
|--------------|-----------|
| `.agents/planning/` | Implementation plans produce testable artifacts |
| `.agents/architecture/` | ADRs are design decisions affecting code |
| `.agents/critique/` | Plan reviews gate implementation decisions; consequential artifacts |
| `.agents/qa/` | QA reports are validation artifacts |
| `.github/` | CI/workflow changes are infrastructure code |
| `.claude/agents/` | Agent prompt files are behavioral code |
| `.github/agents/` | Copilot agent prompts are behavioral code |
| `src/`, `scripts/`, `*.ps1` | Code files always require QA |

### Validation Logic

```powershell
if ($row.Evidence -match '(?i)SKIPPED:\s*investigation-only') {
    $stagedFiles = @(git diff --cached --name-only)
    $implementationFiles = $stagedFiles | Where-Object {
        $file = $_
        $isAllowed = $false
        foreach ($pattern in $investigationAllowlist) {
            if ($file -match $pattern) {
                $isAllowed = $true
                break
            }
        }
        -not $isAllowed
    }
    if ($implementationFiles.Count -gt 0) {
        Fail 'E_INVESTIGATION_HAS_IMPL' @"
Investigation skip claimed but staged files contain implementation artifacts:
  $($implementationFiles -join "`n  ")

Investigation sessions may only stage:
  - .agents/sessions/ (session logs)
  - .agents/analysis/ (investigation outputs)
  - .agents/retrospective/ (learnings)
  - .serena/memories/ (memory updates)
  - .agents/security/ (security assessments)

Remove implementation artifacts or obtain QA validation.
"@
    }
    # Track metrics for investigation-only skips
    Write-Verbose "Investigation-only skip: $($stagedFiles.Count) files"
    # Skip QA requirement for legitimate investigation sessions
    return
}
```

### Mixed Session Recovery Path

When an investigation session discovers code changes are needed:

```text
INVESTIGATION SESSION MODE CHANGE
---------------------------------
1. Complete investigation artifacts (analysis docs, session log)
2. Commit investigation work with "SKIPPED: investigation-only"
3. Start NEW session for code changes (with QA validation)
4. Reference investigation session in implementation session log
```

**Branch Strategy**: Continue on SAME branch. The investigation commit clears staged investigation artifacts before the implementation session begins.

**Rationale**: Clear separation of investigation vs implementation work. Prevents mixed sessions that are hard to validate.

**Session Log Example**:

```markdown
## Decisions

1. During investigation (session 106), discovered authentication bug
2. Implementation deferred to session 107 per ADR-034 mixed-session protocol

## Related Sessions

- Session 106: Investigation that discovered the issue
```

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Session-level change detection | Precise, automatic | Complex, fragile session boundaries | Implementation complexity too high |
| File-based exemption (sessions/*.md only) | Automatic | Too narrow, doesn't cover memory updates | Missing legitimate use cases |
| QA categories for investigations | Consistent documentation | Overhead for simple investigations | Scope creep, QA not suited for investigation reports |
| **Explicit investigation mode** | Simple, auditable, conservative | Requires explicit opt-in | **CHOSEN**: Best trade-off |

### Trade-offs

| Trade-off | Resolution |
|-----------|------------|
| Trust-based (could be misused) | Staged-file guardrail prevents false claims |
| Manual opt-in required | Consistent with existing `docs-only` pattern |
| Pattern proliferation risk | Define skip-reason enum in future iteration |

## Consequences

### Positive

- 29.4% of sessions no longer require workarounds
- Eliminates `--no-verify` normalization for legitimate investigation sessions
- Audit trail preserved (explicit evidence pattern documents intent)
- Consistent with existing `SKIPPED: docs-only` pattern

### Negative

- Agents must learn about investigation-only mode (documentation required)
- Trust element remains (guardrail is enforcement, not prevention)
- Two commit types for mixed sessions (investigation + implementation)

### Neutral

- CI backstop can be added as defense-in-depth (P2 enhancement)
- Bypass logging can be implemented separately (P1 enhancement)

### Confirmation

Implementation compliance verified by:

1. Pester unit tests for all validation paths (8 test cases defined)
2. Pre-commit hook self-test with investigation-only session
3. Integration test: commit with staged `.agents/sessions/` only, verify PASS
4. Integration test: commit with staged `src/` + investigation evidence, verify FAIL
5. Metrics dashboard showing investigation-only skip count vs `--no-verify` bypass rate

## Reversibility Assessment

| Aspect | Assessment |
|--------|------------|
| **Rollback capability** | PASS - Remove evidence pattern check from Validate-Session.ps1. No data format changes. |
| **Vendor lock-in** | N/A - No external dependencies introduced |
| **Exit strategy** | Remove 15-20 lines from validator script, update SESSION-PROTOCOL.md |
| **Legacy impact** | LOW - Existing sessions with investigation-only evidence would fail validation after rollback. Acceptable since evidence was advisory. |
| **Data migration** | NONE - No data format changes. Session log format unchanged. |

## Implementation Notes

### Phase 1: Validator Update (P0)

1. Define `$investigationAllowlist` constant in `Validate-Session.ps1`
2. Add `(?i)SKIPPED:\s*investigation-only` evidence pattern check
3. Implement staged-file allowlist verification
4. Add clear error message for failed guardrail checks
5. Add metrics counter for investigation-only skips
6. Unit test all validation paths

### Phase 2: Documentation (P0)

1. Update SESSION-PROTOCOL.md Phase 2.5:

   ```markdown
   4. The agent MAY skip QA validation when:
      a. All modified files are documentation files (editorial changes only) -> Use "SKIPPED: docs-only"
      b. Session is investigation-only (no code/config changes) -> Use "SKIPPED: investigation-only"
   ```

2. Add mixed-session recovery workflow to SESSION-PROTOCOL.md
3. Document memory-update sessions as valid investigation sessions
4. Update session log template with investigation-only example

### Phase 3: Defense-in-Depth (P1-P2)

1. (P1) Create skill "Check QA skip eligibility" for agent self-service
2. (P2) Implement CI backstop validation
3. (P2) Add `--no-verify` bypass logging

### Metrics Collection

| Metric | Target | Measurement |
|--------|--------|-------------|
| Investigation-only skip rate | Track baseline | Count per week from validator logs |
| `--no-verify` bypass rate | Reduce by 50% | Git hook audit log analysis |
| False positive rate | < 5% | Sessions incorrectly flagged for QA |
| Adoption rate | > 80% of investigation sessions | Pattern usage in session logs |

### Test Cases

| Scenario | Expected Result |
|----------|-----------------|
| Investigation session with only `.agents/sessions/` staged | PASS |
| Investigation session with `.serena/memories/` + session log | PASS |
| Investigation session with `.agents/security/SA-*.md` staged | PASS |
| Investigation session with `.agents/planning/PRD.md` staged | FAIL (implementation artifact) |
| Investigation session with `.agents/critique/` staged | FAIL (consequential artifact) |
| Investigation session with `.github/workflows/ci.yml` staged | FAIL (infrastructure code) |
| Investigation session with `src/component.ts` staged | FAIL (code file) |
| Investigation session with `.claude/agents/agent.md` staged | FAIL (agent prompt file) |
| Investigation session with `.github/agents/copilot.md` staged | FAIL (copilot agent prompt) |
| No staged files, investigation-only evidence | PASS (no commit occurs) |

## Related Decisions

- ADR-004: Pre-commit Hook Architecture
- ADR-006: Thin Workflows, Testable Modules

## References

- `.agents/analysis/pre-commit-qa-investigation-sessions-gap.md` - Problem analysis
- `.agents/analysis/investigation-session-patterns-analyst-report.md` - Analyst findings
- `.agents/architecture/ASSESSMENT-session-qa-validation-options.md` - Architect assessment
- `.agents/security/SA-pre-commit-qa-skip-options.md` - Security assessment
- `.agents/critique/investigation-qa-exemption-proposal-critique.md` - Critic review
- `scripts/Validate-Session.ps1` - Implementation target (lines 336-351)
- `.agents/SESSION-PROTOCOL.md` - Documentation target (lines 252-274)

---

## ADR Review Debate Summary

### Round 1: Independent Reviews

Six agents reviewed ADR-034 independently:

| Agent | Verdict | Key Findings |
|-------|---------|--------------|
| Architect | CONDITIONAL | Missing MADR frontmatter, reversibility, confirmation |
| Critic | NEEDS REVISION | Memory regex subdirectory issue, critique justification |
| Independent Thinker | CONDITIONAL | Questions problem severity, critique inclusion |
| Security | CONDITIONAL | Missing `.agents/security/` path |
| Analyst | NEEDS REVISION | Session 106 verification (resolved: file exists) |
| High-Level Advisor | APPROVE WITH CONDITIONS | Metrics plan, critique loophole |

### Conflict Resolutions

| Conflict | Ruling | Rationale |
|----------|--------|-----------|
| `.agents/critique/` in allowlist | EXCLUDE | 5/6 agents flagged as loophole; consequential artifacts |
| Missing `.agents/security/` path | ADD | Security assessments are investigation outputs |
| Missing `.agents/handoffs/` path | REJECT | Handoffs coordinate implementation, not investigation |
| Session 106 evidence | VALID | File exists at expected path |
| CI backstop priority | KEEP P2 | Pre-commit is primary enforcement |
| Scope split | NO SPLIT | Single coherent capability |

### Changes Applied

1. Added MADR 4.0 frontmatter with decision-makers and consulted
2. Removed `.agents/critique/` from allowlist (loophole)
3. Added `.agents/security/` to allowlist (investigation output)
4. Fixed memory regex to `^\.serena/memories($|/)` for subdirectory support
5. Added Reversibility Assessment section
6. Added Confirmation section with verification criteria
7. Added Metrics Collection table
8. Assigned allowlist owner (Architect agent)
9. Updated test cases for new allowlist
10. Clarified mixed-session branch strategy

### Consensus Status

All agents converged on Option 2 with modifications applied. No blocking concerns remain.

---

*Template Version: 1.0*
*Created: 2025-12-30*
*ADR Review: Complete (Round 1)*
