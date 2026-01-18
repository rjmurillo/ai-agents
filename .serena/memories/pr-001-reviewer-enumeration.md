# Skill-PR-001: Reviewer Enumeration

**Statement**: Enumerate ALL reviewers before triaging to avoid single-bot blindness.

```bash
gh pr view PR --json reviews --jq '.reviews[].author.login' | sort -u
```

## Related

- [pr-002-independent-comment-parsing](pr-002-independent-comment-parsing.md)
- [pr-003-verification-count](pr-003-verification-count.md)
- [pr-006-reviewer-signal-quality](pr-006-reviewer-signal-quality.md)
- [pr-156-review-findings](pr-156-review-findings.md)
- [pr-308-devops-review](pr-308-devops-review.md)
