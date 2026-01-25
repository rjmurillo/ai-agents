# Skill-PR-001: Reviewer Enumeration

**Statement**: Enumerate ALL reviewers before triaging to avoid single-bot blindness.

```bash
gh pr view PR --json reviews --jq '.reviews[].author.login' | sort -u
```

## Related

- [pr-156-review-findings](pr-156-review-findings.md)
- [pr-320c2b3-refactoring-analysis](pr-320c2b3-refactoring-analysis.md)
- [pr-52-retrospective-learnings](pr-52-retrospective-learnings.md)
- [pr-52-symlink-retrospective](pr-52-symlink-retrospective.md)
- [pr-753-remediation-learnings](pr-753-remediation-learnings.md)
