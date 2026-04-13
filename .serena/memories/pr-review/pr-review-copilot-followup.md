# PR Review: Copilot Follow-Up PR Detection

## Skill-PR-Copilot-001: Follow-Up PR Pattern

**Statement**: Detect Copilot follow-up PRs using branch pattern `copilot/sub-pr-{original}`.

**Atomicity**: 96%

## Categories

| Category | Indicator | Action |
|----------|-----------|--------|
| DUPLICATE | No/minimal changes | Close with commit ref |
| SUPPLEMENTAL | Additional issues | Evaluate for merge |
| INDEPENDENT | Unrelated | Close with explanation |

## Detection

```bash
# Find Copilot follow-up PRs for a given PR
gh pr list --json number,headRefName --jq '.[] | select(.headRefName | startswith("copilot/sub-pr-"))'
```

## Related

- [pr-156-review-findings](pr-156-review-findings.md)
- [pr-320c2b3-refactoring-analysis](pr-320c2b3-refactoring-analysis.md)
- [pr-52-retrospective-learnings](pr-52-retrospective-learnings.md)
- [pr-52-symlink-retrospective](pr-52-symlink-retrospective.md)
- [pr-753-remediation-learnings](pr-753-remediation-learnings.md)
