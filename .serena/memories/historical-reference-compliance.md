# Historical Reference Protocol Compliance

**Created**: 2026-01-01
**Session**: 123
**Commit**: `9b2abfa`
**PR**: #733

## Summary

Audit of `.agents/` directories for historical reference protocol compliance per `.agents/governance/historical-reference-protocol.md`.

## Key Findings

### Compliance Rate

Most documents are compliant. Out of 100+ references scanned, only 8 actual violations found.

### Common Violation Patterns

1. **Reference sections missing dates**: The `## References` section at end of analysis docs often lists PR/issue numbers without dates
2. **Commit references without dates**: `commit abc123` instead of `commit abc123 (YYYY-MM-DD)`

### False Positives to Ignore

1. **Documentation examples**: Anti-pattern examples in protocol docs themselves
2. **Template placeholders**: `[What was decided]` in ADR templates
3. **In-context references**: Documents with date in header provide context for internal references

## Audit Methodology

Search patterns used:

```bash
# Vague references
grep -rn "was done previously|original implementation|as decided|per our previous" .agents/

# ADR references without commit
grep -rn "per ADR-|see ADR-|from ADR-|in ADR-" .agents/ | grep -v "[a-f0-9]{7}"

# PR/Issue references without dates
grep -rn "PR #[0-9]+[^(]" .agents/
grep -rn "Issue #[0-9]+[^(0-9]" .agents/
```

## Files Fixed

| File | Violations | Fix |
|------|------------|-----|
| `003-quality-gate-comment-caching-rca.md` | 5 | Added dates to commit, PR, and issue refs |
| `281-similar-pr-detection-review.md` | 3 | Added dates to PR and issue refs |

## Lookup Commands

Getting dates for references:

```bash
# Commit date
git log --format="%ad" --date=short {sha} -1

# PR/Issue date
gh pr view {number} --json createdAt --jq '.createdAt[:10]'
gh issue view {number} --json createdAt --jq '.createdAt[:10]'
```

## Related

- Protocol: `.agents/governance/historical-reference-protocol.md`
- Compliance plan: `.agents/planning/historical-reference-compliance-plan.md`
- Session: `.agents/sessions/2026-01-01-session-123-historical-reference-compliance.md`
