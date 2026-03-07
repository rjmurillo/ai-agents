# Skill-Validation-001: Validation Script False Positives

**Statement**: When creating validation scripts, distinguish between examples/anti-patterns and production code to prevent false positives.

**Evidence**: 3/14 path violations were intentional anti-pattern examples in explainer.md

**Atomicity**: 88%

## Mitigation Strategies

1. Skip code fence blocks during validation
2. Add `<!-- skip-validation -->` comment mechanism
3. Maintain allowlist for known pedagogical examples
4. Document false positives in validation output

## Pattern

```powershell
# Skip code fences
$insideCodeFence = $false
foreach ($line in $content) {
    if ($line -match '^```') {
        $insideCodeFence = -not $insideCodeFence
        continue
    }
    if (-not $insideCodeFence) {
        # Validate this line
    }
}
```

## Related

- [validation-006-self-report-verification](validation-006-self-report-verification.md)
- [validation-007-cross-reference-verification](validation-007-cross-reference-verification.md)
- [validation-007-frontmatter-validation-compliance](validation-007-frontmatter-validation-compliance.md)
- [validation-474-adr-numbering-qa-final](validation-474-adr-numbering-qa-final.md)
- [validation-anti-patterns](validation-anti-patterns.md)
