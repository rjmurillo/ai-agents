# Validation & Quality Skills

**Extracted**: 2025-12-16
**Source**: `.agents/retrospective/phase1-remediation-pr43.md`

## Skill-Validation-001: Validation Script False Positives

**Statement**: When creating validation scripts, distinguish between examples/anti-patterns and production code to prevent false positives

**Context**: Any validation script or automated checker

**Evidence**: 3/14 path violations were intentional anti-pattern examples in explainer.md

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 8/10

**Mitigation Strategies**:

1. Skip code fence blocks during validation
2. Add `<!-- skip-validation -->` comment mechanism
3. Maintain allowlist for known pedagogical examples
4. Document false positives in validation output

---

## Skill-Validation-002: Pedagogical Error Messages

**Statement**: Validation scripts should be pedagogical - error messages should teach the standard, not just report violations

**Context**: Any validation script or linter

**Evidence**: Path validation script includes remediation steps, examples, references explaining why/what/how

**Atomicity**: 90%

**Tag**: helpful

**Impact**: 9/10

**Pattern**:

```text
ERROR: Incorrect path reference at explainer.md:45
  Found: path/to/file
  Expected: [path/to/file](path/to/file)
  
  WHY: Markdown links enable navigation and prevent broken references
  FIX: Wrap path in link syntax: [display](target)
  REF: See .markdownlint-cli2.yaml for configuration
```

---

## Skill-Validation-003: Pre-Existing Issue Triage

**Statement**: When introducing new validation, establish baseline and triage pre-existing violations separately from new work

**Context**: Adding new validators to existing codebases

**Evidence**: Validation script found 14 pre-existing issues requiring separate triage to avoid scope creep

**Atomicity**: 92%

**Tag**: helpful

**Impact**: 9/10

**Implementation**:

1. Run validator and capture baseline count
2. Create exception list or snapshot for existing violations
3. New code must pass validation (zero tolerance)
4. Schedule separate remediation for pre-existing issues
5. Gradual rollout: warn → error over time

---

## Related Documents

- Source: `.agents/retrospective/phase1-remediation-pr43.md`
- Related: skills-linting (Skill-Lint-002 false positives)
