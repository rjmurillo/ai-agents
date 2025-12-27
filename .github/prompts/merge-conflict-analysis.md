# Merge Conflict Analysis

You are analyzing merge conflicts for PR #${{ pr-number }} to determine resolution strategy.

## Workflow (from merge-resolver skill)

1. **Identify conflicts** - Review the conflicted files
2. **Analyze each conflict** - Use git blame context provided
3. **Determine intent** - Classify changes by type
4. **Recommend resolution** - Keep, merge, or discard based on analysis

## Intent Classification

| Type | Indicators | Priority |
|------|------------|----------|
| Bugfix | "fix", "bug", "patch", "hotfix" in message; small, targeted change | Highest |
| Security | "security", "vuln", "CVE" in message | Highest |
| Refactor | "refactor", "cleanup", "rename"; no behavior change | Medium |
| Feature | "feat", "add", "implement"; new functionality | Medium |
| Style | "style", "format", "lint"; whitespace/formatting only | Lowest |

## Resolution Strategies (from strategies.md)

### Additive Changes
Both sides add new content - combine both additions.

### Moved Code
One side moves code, other modifies - apply modifications to new location.

### Conflicting Logic
Bugfix wins over feature. Security fix wins over everything. More recent wins if both are features.

### Formatting Conflicts
Accept either version, prefer consistency with surrounding code.

### Package Lock Conflicts
Accept base version, regenerate.

## Auto-Resolvable Files (always accept theirs/main)

These files are auto-generated or session-specific where main is authoritative:
- `.agents/*` - Session artifacts
- `.serena/*` - Serena memories
- `.claude/skills/*/*.md` - Skill definitions
- `templates/*` - Template files
- `src/copilot-cli/*`, `src/vs-code-agents/*`, `src/claude/*` - Platform agents
- `.github/agents/*`, `.github/prompts/*` - GitHub configs
- `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml` - Lock files

## Required Output Format

Output a JSON object for each conflicted file:

```json
{
  "resolutions": [
    {
      "file": "<path>",
      "strategy": "theirs|ours|combine",
      "reasoning": "<1-2 sentences explaining why based on git history analysis>",
      "combined_content": "<if strategy is combine, the fully resolved file content>"
    }
  ]
}
```

Strategy meanings:
- `theirs`: Accept base branch (main) version - use `git checkout --theirs`
- `ours`: Keep PR branch version - use `git checkout --ours`
- `combine`: Manual merge needed - provide complete `combined_content`

VERDICT: PASS if all conflicts can be resolved with clear strategy.
VERDICT: CRITICAL_FAIL if conflicts cannot be resolved (need human intervention).
