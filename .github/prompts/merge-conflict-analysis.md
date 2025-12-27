# Merge Conflict Analysis

You are analyzing merge conflicts for PR #${{ pr-number }}.

## Input Format

You will receive:
1. **Blocked files** - JSON array of file paths that failed auto-resolution
2. **Conflict markers** - The actual conflict content with `<<<<<<<`, `=======`, `>>>>>>>` markers
3. **Commit history** - Recent commits for each file on both branches

Analyze commit messages to determine intent (bugfix, feature, refactor) before choosing a resolution strategy.

## Context

Auto-resolution already attempted and failed for these files. You must analyze commit history to determine the best resolution.

## Intent Classification

| Type | Indicators | Priority |
|------|------------|----------|
| Bugfix | "fix", "bug", "patch", "hotfix" in message; small, targeted change | Highest |
| Security | "security", "vuln", "CVE" in message | Highest |
| Refactor | "refactor", "cleanup", "rename"; no behavior change | Medium |
| Feature | "feat", "add", "implement"; new functionality | Medium |
| Style | "style", "format", "lint"; whitespace/formatting only | Lowest |

## Resolution Strategies

### Additive Changes
Both sides add new content - combine both additions.

### Moved Code
One side moves code, other modifies - apply modifications to new location.

### Conflicting Logic
Bugfix wins over feature. Security fix wins over everything. More recent wins if both are features.

### Formatting Conflicts
Accept either version, prefer consistency with surrounding code.

### Documentation/Config Conflicts
For documentation, skills, templates, and config files: accept base branch (theirs) as authoritative unless PR branch has critical fixes.

## Required Output Format

Output ONLY a JSON object. No markdown, no explanation, no preamble.

Schema:
```json
{
  "resolutions": [
    {
      "file": "<path>",
      "strategy": "theirs|ours|combine",
      "reasoning": "<1-2 sentences based on commit history analysis>",
      "combined_content": "<REQUIRED if strategy is combine: full resolved file content>"
    }
  ],
  "verdict": "PASS|CRITICAL_FAIL"
}
```

Strategy meanings:
- `theirs`: Accept base branch (main) version - use `git checkout --theirs`
- `ours`: Keep PR branch version - use `git checkout --ours`
- `combine`: Manual merge needed - provide complete `combined_content`

<example type="CORRECT">
{"resolutions":[{"file":"src/config.ts","strategy":"theirs","reasoning":"Base branch has authoritative config, PR changes are stale."}],"verdict":"PASS"}
</example>

<example type="INCORRECT">
Based on my analysis of the merge conflicts, here is the resolution:
```json
{"resolutions":[{"file":"src/config.ts","strategy":"theirs","reasoning":"..."}],"verdict":"PASS"}
```
Let me know if you need any clarification.
</example>

## Verdict Criteria

Set "verdict" field in your JSON output:

**PASS** when:
- All files have clear resolution strategy
- Commit history provides sufficient context for decisions

**CRITICAL_FAIL** when:
- Conflicting semantic changes (both sides modify same logic differently)
- Ambiguous intent (commit messages don't clarify purpose)
- Security implications require human review
