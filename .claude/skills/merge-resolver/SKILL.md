---
name: merge-resolver
description: Resolve merge conflicts intelligently using git history. Use when given a PR number (e.g., "#123") to analyze and resolve merge conflicts. Fetches PR context, identifies conflicted files, uses git blame and commit history to infer developer intent, and applies resolution strategies based on change type (bugfix, feature, refactor). Combines non-conflicting changes when appropriate. Stages resolved files for commit.
---

# Merge Resolver

Resolve merge conflicts by analyzing git history and commit intent.

## Workflow

1. **Fetch PR context** - Get title, description, commits
2. **Identify conflicts** - Find conflicted files in working directory
3. **Analyze each conflict** - Use git blame and commit messages
4. **Determine intent** - Classify changes by type
5. **Apply resolution** - Keep, merge, or discard based on analysis
6. **Stage resolved files** - Prepare for commit
7. **Validate session protocol** - BLOCKING: Run validation before push

## Step 1: Fetch PR Context

```bash
# Get PR metadata
gh pr view <number> --json title,body,commits,headRefName,baseRefName

# Checkout the PR branch
gh pr checkout <number>

# Attempt merge with base (creates conflict markers)
git merge origin/<base-branch> --no-commit
```

## Step 2: Identify Conflicts

```bash
# List conflicted files
git diff --name-only --diff-filter=U

# Show conflict details
git status --porcelain | grep "^UU"
```

## Step 3: Analyze Each Conflict

For each conflicted file:

```bash
# View the conflict
git diff --check

# Get blame for conflicting lines (base version)
git blame <base-branch> -- <file> | grep -n "<line-content>"

# Get blame for conflicting lines (head version)
git blame HEAD -- <file> | grep -n "<line-content>"

# Show commits touching this file on each branch
git log --oneline <base-branch>..<head-branch> -- <file>
git log --oneline <head-branch>..<base-branch> -- <file>

# View specific commit details
git show --stat <commit-sha>
```

## Step 4: Determine Intent

Classify each side's changes:

| Type | Indicators | Priority |
|------|------------|----------|
| Bugfix | "fix", "bug", "patch", "hotfix" in message; small, targeted change | Highest |
| Security | "security", "vuln", "CVE" in message | Highest |
| Refactor | "refactor", "cleanup", "rename"; no behavior change | Medium |
| Feature | "feat", "add", "implement"; new functionality | Medium |
| Style | "style", "format", "lint"; whitespace/formatting only | Lowest |

## Step 5: Apply Resolution

**Decision Framework:**

1. **Same intent, compatible changes** - Merge both
2. **Bugfix vs feature** - Bugfix wins, integrate feature around it
3. **Conflicting logic** - Prefer the more recent or more tested change
4. **Style conflicts** - Accept either, prefer consistency with surrounding code
5. **Deletions vs modifications** - Investigate why; deletion usually intentional

**Resolution Commands:**

```bash
# Accept theirs (base branch)
git checkout --theirs <file>

# Accept ours (PR branch)
git checkout --ours <file>

# Manual edit then mark resolved
git add <file>
```

**For manual resolution:**

1. Open file in editor
2. Remove conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`)
3. Combine changes logically based on intent analysis
4. Verify syntax and logic
5. Stage the file

## Step 6: Stage and Verify

```bash
# Stage all resolved files
git add <resolved-files>

# Verify no remaining conflicts
git diff --check

# Show staged changes
git diff --cached --stat
```

## Step 7: Validate Session Protocol (BLOCKING)

**MUST complete before pushing.** This step prevents CI failures from incomplete session logs.

### Why This Matters

Session protocol validation is a CI blocking gate. Pushing without completing session requirements causes:

- CI failures with "MUST requirement(s) not met" errors
- Wasted review cycles
- Confusion about root cause (often misidentified as template sync issues)

### Validation Steps

```bash
# 1. Ensure session log exists
SESSION_LOG=$(ls -t .agents/sessions/*.md 2>/dev/null | head -1)
if [ -z "$SESSION_LOG" ]; then
    echo "ERROR: No session log found. Create one before pushing."
    exit 1
fi

# 2. Run session protocol validator
pwsh scripts/Validate-Session.ps1 -SessionLogPath "$SESSION_LOG"

# 3. If validation fails, fix issues before proceeding
if [ $? -ne 0 ]; then
    echo "ERROR: Session protocol validation failed."
    echo "Complete all MUST requirements in your session log before pushing."
    exit 1
fi
```

### Session End Checklist (REQUIRED)

Before pushing, verify your session log contains:

| Req | Step | Status |
|-----|------|--------|
| MUST | Complete session log (all sections filled) | [ ] |
| MUST | Update Serena memory (cross-session context) | [ ] |
| MUST | Run markdown lint | [ ] |
| MUST | Route to qa agent (feature implementation) | [ ] |
| MUST | Commit all changes (including .serena/memories) | [ ] |
| MUST NOT | Update `.agents/HANDOFF.md` directly | [ ] |

### Common Failures

| Error | Cause | Fix |
|-------|-------|-----|
| `E_TEMPLATE_DRIFT` | Session checklist outdated | Copy canonical checklist from SESSION-PROTOCOL.md |
| `E_QA_EVIDENCE` | QA row checked but no report path | Add QA report or use "SKIPPED: docs-only" for docs-only sessions |
| `E_DIRTY_WORKTREE` | Uncommitted changes | Stage and commit all files including `.agents/` |

## Resolution Strategies

See `references/strategies.md` for detailed patterns:

**Code Conflicts:**

- Combining additive changes
- Handling moved code
- Resolving import conflicts
- Dealing with deleted code
- Conflicting logic resolution

**Infrastructure Conflicts:**

- Package lock files (regenerate, don't merge)
- Configuration files (JSON/YAML semantic merge)
- Database migrations (renumber, preserve order)

**Documentation Conflicts:**

- Numbered documentation (ADR, RFC) - renumber incoming to next available
- Template-generated files - resolve in template, regenerate outputs
- Rebase add/add conflicts - per-commit resolution during rebase

## Auto-Resolution Script

For automated conflict resolution in CI/CD, use `scripts/Resolve-PRConflicts.ps1`:

```powershell
# Resolve conflicts for a PR
pwsh .claude/skills/merge-resolver/scripts/Resolve-PRConflicts.ps1 \
    -PRNumber 123 \
    -BranchName "fix/my-feature" \
    -TargetBranch "main"
```

### Auto-Resolvable Files

The following files are automatically resolved by accepting the target branch version:

| Pattern | Rationale |
|---------|-----------|
| `.agents/*` | Session artifacts, constantly changing |
| `.serena/*` | Serena memories, auto-generated |
| `.claude/skills/*/*.md` | Skill definitions, main is authoritative |
| `.claude/commands/*` | Command definitions, main is authoritative |
| `.claude/agents/*` | Agent definitions, main is authoritative |
| `templates/*` | Template files, main is authoritative |
| `src/copilot-cli/*` | Platform agent definitions |
| `src/vs-code-agents/*` | Platform agent definitions |
| `src/claude/*` | Platform agent definitions |
| `.github/agents/*` | GitHub agent configs |
| `.github/prompts/*` | GitHub prompts |
| `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml` | Lock files, regenerate from main |

### Script Output

Returns JSON:

```json
{
  "Success": true,
  "Message": "Successfully resolved conflicts for PR #123",
  "FilesResolved": [".agents/HANDOFF.md"],
  "FilesBlocked": []
}
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success - conflicts resolved and pushed |
| 1 | Failure - conflicts in non-auto-resolvable files |

### Security

ADR-015 compliance:

- Branch name validation (prevents command injection)
- Worktree path validation (prevents path traversal)
- Handles both GitHub Actions runner and local environments
