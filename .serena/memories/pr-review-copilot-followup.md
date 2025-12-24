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
