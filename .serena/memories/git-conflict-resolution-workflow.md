# Skill-Git-004: Conflict Resolution Workflow

**Statement**: Resolve PR merge conflicts by checking out branch, merging main, committing resolution

**Context**: When PR shows merge conflict status. Use for systematic batch conflict resolution across multiple PRs. Applies to stale branches that diverged from main.

**Evidence**: 2025-12-24 PR monitoring: 14 merge conflicts across 6 PRs (PRs #300, #299, #285, #255, #247, #235) resolved with 100% success rate using systematic 3-step pattern: checkout → merge → commit. No failures, no rework required. Lines 196-199 of retrospective.

**Atomicity**: 90% | **Impact**: 9/10

## Pattern

Systematic conflict resolution (3 steps):

### Step 1: Checkout PR branch

```bash
git fetch origin
git checkout -b <branch-name> origin/<branch-name>
```

### Step 2: Merge main and resolve conflicts

```bash
git merge main
# If conflicts occur:
# 1. Review conflict markers in files
# 2. Edit files to resolve conflicts
# 3. Remove conflict markers (<<<<<<<, =======, >>>>>>>)
# 4. Verify resolution builds/tests pass
```

### Step 3: Commit and push resolution

```bash
git add .
git commit -m "Resolve merge conflicts with main"
git push origin <branch-name>
```

### Batch Resolution Pattern

For multiple PRs with conflicts:

```bash
# Iterate through each PR
for pr in 300 299 285 255 247 235; do
  gh pr checkout "$pr"
  git merge main
  # Resolve conflicts...
  git add .
  git commit -m "Resolve merge conflicts with main"
  git push
done
```

## Anti-Pattern

Skipping verification step after resolution:

```bash
# AVOID: Commit without verifying
git merge main
# Resolve conflicts...
git add .
git commit  # No build/test verification!
```

**Risk**: Conflicts may be syntactically resolved but semantically broken (code compiles but logic fails).

**Best Practice**: After resolving conflicts, run project tests or build to verify semantic correctness before committing.

**Evidence**: All 14 conflicts resolved successfully because verification was performed before commit.
