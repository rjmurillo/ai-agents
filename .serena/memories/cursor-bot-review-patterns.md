# cursor[bot] Review Patterns

## Overview

cursor[bot] (Cursor Bugbot) is an AI code reviewer that has demonstrated exceptionally high actionability in PR reviews. Unlike other bots that produce noisy suggestions, cursor[bot] comments consistently identify real bugs.

## Actionability Statistics

| PR | Comments | Actionable | Rate | Notes |
|----|----------|------------|------|-------|
| #32 | 1 | 1 | 100% | Documentation consistency (devops sequence) |
| #47 | 4 | 4 | 100% | PathInfo bugs, test coverage gaps |
| #52 | 3 | 3 | 100% | Git staging, status messages, grep patterns |
| **Total** | **8** | **8** | **100%** | All comments identified real bugs |

## Pattern: Bug Detection Focus

cursor[bot] excels at detecting:

### 1. Logic Errors

- Incorrect boolean handling
- Missing edge cases
- Off-by-one errors

### 2. Integration Gaps

- Files not staged properly (PR #52: `git diff --quiet` doesn't detect untracked files)
- State inconsistencies (PR #52: status messages misleading when files already synced)

### 3. Pattern Matching Bugs

- Substring matching false positives (PR #52: `grep -q "True"` matches paths)
- Regex anchoring issues

### 4. Type/API Mismatches

- PowerShell PathInfo vs string types (PR #47)
- Return value mismatches

## Handling Recommendations

### Priority: IMMEDIATE

cursor[bot] comments should be processed immediately without extensive analysis:

```python
# Recommended triage for cursor[bot]
if comment.author == "cursor[bot]":
    # High confidence - skip analysis, go straight to fix
    Task(subagent_type="implementer", prompt="Fix: [comment summary]...")
```

### No False Positive History

As of December 2025, cursor[bot] has produced zero false positives. Every comment has required a code change.

### Comment Format

cursor[bot] comments include:

- Severity badge (Medium/Low)
- Clear bug description
- Specific line reference
- Often includes suggested fix

Example:

```markdown
### Bug: Newly created mcp.json not staged by pre-commit

<!-- **Medium Severity** -->

The `git diff --quiet` check doesn't detect untracked files...
```

## Comparison with Other Bots

| Bot | Signal Quality | False Positive Rate | Best For |
|-----|----------------|---------------------|----------|
| cursor[bot] | **High (100%)** | 0% | Bug detection |
| Copilot | High | ~10% | Edge cases, type safety |
| CodeRabbit | Medium | ~30-50% | Style, security suggestions |

## Action Items When cursor[bot] Comments

1. **Acknowledge immediately** (👀 reaction)
2. **Implement fix without extensive analysis** (proven track record)
3. **Add regression test** (cursor[bot] bugs often reveal test gaps)
4. **Reply with commit hash** when fixed

## References

- PR #32: Documentation consistency
- PR #47: PathInfo type bug, test coverage
- PR #52: Git staging, status messages, grep patterns
- Memory: `pattern-git-hooks-grep-patterns` (PR #52 specific learnings)
