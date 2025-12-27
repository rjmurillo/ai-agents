**Statement**: Verify code exists in target branch before claiming it is missing.

**Context**: When claiming issue X blocks PR Y due to missing implementation

**Evidence**: PR #402 session - Claimed issue #338 (retry logic) was blocking. Reality: PR #370 merged #338 fixes, PR #402 based on main which included them. Made confident claim without verification.

**Atomicity**: 97% | **Impact**: 10/10

## Pattern

Before claiming code is missing:

```bash
# Step 1: Check target branch
git log origin/main --oneline --grep="<issue-number>"

# Step 2: Search for implementation
grep -r "<function-name>" <relevant-paths>

# Step 3: Check PR base
git log HEAD --oneline | head -20  # Recent commits
git diff origin/main...HEAD  # What's NEW in this PR
```

If claiming "issue #X blocks this work":

1. Verify fix is NOT already merged
2. Check if target branch includes the dependency
3. Search codebase for expected symbols/patterns

## Anti-Pattern

```text
[HARMFUL] Claim code is missing without verification
- Agent: "Issue #338 retry logic is needed before this PR can merge"
- Reality: git log shows PR #370 merged #338 fixes last week
- Impact: Misleading comments, wasted investigation time
```

**Why harmful**: Makes confident claims about missing code without checking if it exists. Creates false blockers.
