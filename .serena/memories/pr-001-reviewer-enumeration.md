# Skill-PR-001: Reviewer Enumeration

**Statement**: Enumerate ALL reviewers before triaging to avoid single-bot blindness.

```bash
gh pr view PR --json reviews --jq '.reviews[].author.login' | sort -u
```
