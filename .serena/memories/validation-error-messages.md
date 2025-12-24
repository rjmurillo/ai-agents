# Skill-Validation-002: Pedagogical Error Messages

**Statement**: Validation scripts should be pedagogical - error messages should teach the standard, not just report violations.

**Evidence**: Path validation script includes remediation steps, examples, references explaining why/what/how.

**Atomicity**: 90%

## Pattern

```text
ERROR: Incorrect path reference at explainer.md:45
  Found: path/to/file
  Expected: [path/to/file](path/to/file)

  WHY: Markdown links enable navigation and prevent broken references
  FIX: Wrap path in link syntax: [display](target)
  REF: See .markdownlint-cli2.yaml for configuration
```

## Elements of Good Error Messages

| Element | Purpose |
|---------|---------|
| Location | File:Line for quick navigation |
| Found | What was detected (actual) |
| Expected | What should be there (desired) |
| WHY | Rationale for the rule |
| FIX | How to remediate |
| REF | Where to learn more |
