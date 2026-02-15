# Validation: Pedagogical Error Messages

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

## Related

- [validation-001-validation-script-false-positives](validation-001-validation-script-false-positives.md)
- [validation-003-preexisting-issue-triage](validation-003-preexisting-issue-triage.md)
- [validation-004-test-before-retrospective](validation-004-test-before-retrospective.md)
- [validation-005-pr-feedback-gate](validation-005-pr-feedback-gate.md)
- [validation-006-self-report-verification](validation-006-self-report-verification.md)
