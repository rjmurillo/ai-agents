# Skill: Verify Triage Bot PR Closures

## Problem

In Session 100, PRs #202 and #203 were closed by the triage bot with rationale:
> "Superseded Content (already on main): Phase 4.5 Copilot Follow-Up Handling already exists in templates/..."

However, only **template documentation** (inline bash examples) existed on main. The actual **PowerShell implementation** (268 lines with structured JSON output, categorization, tests) was never merged.

## Root Cause

Triage bot matched keywords in the template but didn't verify the actual implementation existed.

## Verification Required

When reviewing bot closures that cite "superseded", "already exists", or "duplicate":

```bash
# 1. Check what the PR was adding
gh pr view {number} --json files -q '.files[].path'

# 2. Verify those files exist on main
for file in $(gh pr view {number} --json files -q '.files[].path'); do
  if [[ -f "$file" ]]; then
    echo "EXISTS: $file"
  else
    echo "MISSING: $file"
  fi
done

# 3. If files don't exist, the bot closure was INCORRECT
```

## Red Flags for Incorrect Bot Closures

| Bot Rationale | Verification |
|---------------|--------------|
| "Superseded" | Check if actual code exists, not just docs |
| "Already exists" | Verify exact file paths, not just concepts |
| "Duplicate" | Compare actual implementations, not titles |

## Recovery

If bot closure was incorrect:

1. Reopen the original PR, OR
2. Cherry-pick/recover from the branch: `git show {branch}:{path}`
3. Create new PR with recovered implementation

## Source

- Session 100 (2025-12-29)
- PRs #202, #203 (incorrectly closed)
- Recovery PR #493
- 268+ lines of implementation recovered

## Related

- [triage-001-verify-before-stale-closure](triage-001-verify-before-stale-closure.md)
