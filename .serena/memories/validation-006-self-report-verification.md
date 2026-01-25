# Skill-Validation-006: Self-Report Verification

## Statement

Agents claiming compliance requires validation; run Validate-SessionEnd.ps1 to verify programmatically

## Context

Don't trust agent self-reported `[COMPLETE]` status without automated verification

## Evidence

**Session-46 (2025-12-20)**: Listed `[COMPLETE]` for all Session End requirements but failed validation script

**Format mismatch**: Used custom format instead of canonical checklist - validation script couldn't parse

**Human audit discovery**: Discrepancy found post-session by manual audit, not automated detection

## Metrics

- **Atomicity**: 91%
- **Impact**: 9/10
- **Category**: validation, verification, trust
- **Created**: 2025-12-20
- **Tag**: helpful
- **Validated**: 1 (Session-46 false positive)

## Pattern

### FALSE POSITIVE: Self-Reported Compliance

```markdown
## Session End Requirements
- [COMPLETE] Retrospective assessment: Not merited
- [COMPLETE] Update HANDOFF.md
- [COMPLETE] Run `npx markdownlint-cli2 --fix "**/*.md"`
- [COMPLETE] Commit changes (commit 3b6559d)
```

Agent claims: "All requirements complete"

Validation script result: FAIL

```powershell
.\scripts\Validate-SessionEnd.ps1 -SessionLogPath "session-46.md"
# ERROR: Session End section incorrect format
# ERROR: Expected [x] checkboxes, found [COMPLETE] status
# Exit code: 1 (FAIL)
```

### TRUE POSITIVE: Programmatic Validation

```markdown
## Session End (COMPLETE ALL before closing)

Session End Requirements:
- [x] Retrospective assessment: Not merited
- [x] Update HANDOFF.md with session summary
- [x] Run `npx markdownlint-cli2 --fix "**/*.md"`
- [x] Commit all changes including .agents/ files

Commit SHA: 3b6559d
```

Validation script result: PASS

```powershell
.\scripts\Validate-SessionEnd.ps1 -SessionLogPath "session-44.md"
# Session End validation: PASS
# Exit code: 0 (SUCCESS)
```

## Anti-Pattern: Checkbox Theater

**Description**: Creating appearance of compliance without meeting verification criteria

**Symptoms**:

- Custom status indicators (`[COMPLETE]`, `[DONE]`, checkmark) instead of canonical `[x]`
- Claims of completion but validation script fails
- Missing required sections with custom equivalents
- Agent assertion vs programmatic verification mismatch

**Evidence**: Session-46 claimed all requirements complete but failed 3 validation checks

## Verification Requirements

Before accepting agent compliance claims:

1. **Automated check**: Run Validate-SessionEnd.ps1
2. **Exit code check**: 0 = PASS, 1 = FAIL
3. **Output review**: Check for specific requirement failures
4. **Reject on failure**: Don't accept self-report if validation fails

## Implementation

**In orchestrator prompt:**

```markdown
When agent claims "Session End complete":

DO NOT accept agent self-report.
DO run Validate-SessionEnd.ps1.
DO check exit code programmatically.
DO reject handoff if validation fails.

Evidence of compliance = validation script PASS, not agent assertion.
```

## Related Skills

- Skill-Protocol-005 (Template Enforcement)
- Skill-Git-001 (Pre-Commit Validation)
- Skill-Orchestration-003 (Handoff Validation Gate)
- Skill-Protocol-002 (Verification-Based Gate Effectiveness)

## Source

`.agents/retrospective/2025-12-20-session-protocol-mass-failure.md` (Learning 6, lines 739-758)

## Related

- [validation-007-cross-reference-verification](validation-007-cross-reference-verification.md)
- [validation-007-frontmatter-validation-compliance](validation-007-frontmatter-validation-compliance.md)
- [validation-474-adr-numbering-qa-final](validation-474-adr-numbering-qa-final.md)
- [validation-anti-patterns](validation-anti-patterns.md)
- [validation-baseline-triage](validation-baseline-triage.md)
