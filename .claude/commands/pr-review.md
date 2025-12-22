# PR Review Command

Respond to PR review comments using the pr-comment-responder workflow with optional parallel execution via git worktrees.

> **Protocol**: This command follows [SESSION-PROTOCOL.md](../../.agents/SESSION-PROTOCOL.md). All MUST requirements apply.

## Usage

```text
/pr-review <PR_NUMBERS> [--parallel] [--cleanup]
```

## Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `PR_NUMBERS` | Comma-separated PR numbers (e.g., `53,141,143`) or `all-open` | Required |
| `--parallel` | Use git worktrees for parallel execution | false |
| `--cleanup` | Clean up worktrees after completion | true |

## Execution Steps

When invoked, execute the following workflow:

### Step 0: Session Initialization (BLOCKING)

Before any PR work, complete the session protocol requirements:

```python
# Phase 1: Serena Initialization (MUST)
mcp__serena__activate_project(project_path)
mcp__serena__initial_instructions()

# Phase 2: Context Retrieval (MUST)
Read(".agents/HANDOFF.md")

# Phase 1.5: Skill Validation (MUST)
Bash("Get-ChildItem -Path '.claude/skills/github/scripts' -Recurse -Filter '*.ps1'")
mcp__serena__read_memory(memory_file_name="skill-usage-mandatory")
Read(".agents/governance/PROJECT-CONSTRAINTS.md")

# Phase 3: Session Log (MUST)
# Create session log at .agents/sessions/YYYY-MM-DD-session-NN.md
# Include Protocol Compliance section from SESSION-PROTOCOL.md template
```

**Work is BLOCKED until all Phase 1, 1.5, 2, and 3 requirements are complete.**

### Step 1: Parse Input

Extract PR numbers from the argument:

```python
# If "all-open", query GitHub for open PRs with review comments
if pr_arg == "all-open":
    # Use: gh pr list --state open --json number,reviewDecision
    # Filter to PRs needing review response
    pass
else:
    pr_numbers = [int(n.strip()) for n in pr_arg.split(",")]
```

### Step 2: Validate PRs

For each PR number:

```powershell
pwsh .claude/skills/github/scripts/pr/Get-PRContext.ps1 -PullRequest {number}
```

Verify:

- PR exists
- PR is open (state != MERGED, CLOSED)
- PR has the current repo as target

### Step 3: Create Worktrees (if --parallel)

For parallel execution, create isolated worktrees with fetched branches:

```bash
# Get PR branch name
branch=$(gh pr view {number} --json headRefName -q '.headRefName')

# Fetch the branch from remote (equivalent to what 'gh pr checkout' does)
git fetch origin "${branch}:${branch}" || git fetch origin "${branch}"

# Create worktree in parent directory
git worktree add ../worktree-pr-{number} {branch}

# If branch ref fails, try origin/ prefix
if [ $? -ne 0 ]; then
    git worktree add ../worktree-pr-{number} "origin/${branch}"
fi
```

> **Note**: For worktrees, we explicitly fetch the branch since `git worktree add`
> doesn't fetch like `gh pr checkout` does. The PowerShell helper script
> `Invoke-BatchPRReview.ps1` handles this automatically.

### Step 3.5: Branch Checkout (MUST for sequential mode)

For non-parallel processing, checkout the PR branch before launching agents:

```bash
# Checkout the PR branch (handles fetch + branch switch)
gh pr checkout {number}
```

This ensures:

- The correct branch is checked out
- Remote changes are fetched
- Branch tracking is configured

### Step 4: Launch Agents

**Sequential (default):**

```python
for pr in pr_numbers:
    # Checkout PR branch first (MUST)
    Bash(f"gh pr checkout {pr}")
    Skill(skill="pr-comment-responder", args=str(pr))
```

**Parallel (--parallel):**

```python
agents = []
for pr in pr_numbers:
    agent = Task(
        subagent_type="pr-comment-responder",
        prompt=f"PR #{pr}",
        run_in_background=True
    )
    agents.append(agent)

# Wait for all agents
for agent_id in agents:
    TaskOutput(task_id=agent_id, block=True, timeout=600000)
```

### Step 5: Verify and Push

For each worktree:

```bash
cd ../worktree-pr-{number}

# Check for uncommitted changes
if [[ -n $(git status --short) ]]; then
    git add .
    git commit -m "chore(pr-{number}): finalize review response session"
    git push origin {branch}
fi

# Verify pushed
git status
```

### Step 6: Cleanup Worktrees (if --cleanup)

```bash
cd {main_repo}

for pr in pr_numbers:
    # Verify worktree is clean and pushed
    worktree_path="../worktree-pr-{pr}"

    cd $worktree_path
    status=$(git status --short)

    if [[ -z "$status" ]]; then
        cd {main_repo}
        git worktree remove $worktree_path
    else
        echo "WARNING: worktree-pr-{pr} has uncommitted changes"
    fi
```

### Step 7: Generate Summary

Output a summary table and complete session requirements:

```markdown
## PR Review Summary

| PR | Branch | Comments | Acknowledged | Implemented | Commit | Status |
|----|--------|----------|--------------|-------------|--------|--------|
| #53 | feat/xyz | 4 | 4 | 3 | abc1234 | COMPLETE |
| #141 | fix/abc | 2 | 2 | 2 | def5678 | COMPLETE |

### Statistics

- **PRs Processed**: 2
- **Comments Reviewed**: 6
- **Fixes Implemented**: 5
- **Commits Pushed**: 2
- **Worktrees Cleaned**: 2
```

### Step 8: Session End Protocol (BLOCKING)

Complete session protocol requirements before closing:

```python
# Phase 1: Documentation Update (MUST)
# Update .agents/HANDOFF.md with session summary and session log link
# Complete session log with tasks, decisions, challenges

# Phase 2: Quality Checks (MUST)
Bash("npx markdownlint-cli2 --fix '**/*.md'")

# Phase 2.5: QA Validation (MUST for feature changes)
# If code was modified (not just documentation):
Task(subagent_type="qa", prompt="Validate PR review changes")

# Phase 3: Git Operations (MUST)
Bash("git add . && git commit -m 'chore: complete PR review session'")

# Phase 4: Retrospective (SHOULD for significant sessions)
# If multiple PRs processed or significant challenges:
Task(subagent_type="retrospective", prompt="Extract learnings from PR review session")
```

**Session is NOT complete until all MUST requirements are verified.**

## Error Recovery

| Scenario | Action |
|----------|--------|
| PR not found | Log warning, skip PR, continue |
| Branch conflict | Log error, skip PR, continue |
| Agent timeout | Log partial status, force cleanup |
| Push rejection | Retry with `--force-with-lease`, report if fails |
| Merge conflict | Log conflict, skip cleanup, report for manual resolution |

## Examples

```bash
# Single PR
/pr-review 194

# Multiple PRs sequentially
/pr-review 53,141,143

# Multiple PRs in parallel with worktrees
/pr-review 53,141,143,194,199,201,202,206 --parallel

# All open PRs needing review
/pr-review all-open --parallel

# Skip cleanup (keep worktrees for inspection)
/pr-review 194 --parallel --cleanup=false
```

## Critical Constraints (MUST)

When using `--parallel` with worktrees, the following constraints are **BLOCKING**:

### 1. Worktree Isolation (MUST)

**ALL changes MUST be contained within the assigned worktree.**

- Agents MUST NOT write files to the main repository directory
- Agents MUST NOT write files to other PR worktrees
- Agents MUST NOT modify shared resources outside their worktree

**Violation consequence**: Work leaks between PRs, potential data corruption, merge conflicts.

### 2. Working Directory (MUST)

**Agents MUST set working directory to their worktree before any file operations.**

```bash
# CORRECT: Work inside worktree
cd ../worktree-pr-{number}
# All file operations happen here

# WRONG: Working from main repo
cd /path/to/main/repo
# Writing to ../worktree-pr-{number}/file.md  # VIOLATION - path traversal
```

### 3. Path Validation (MUST)

**All file paths MUST be relative to the worktree root or use absolute paths within the worktree.**

```python
# CORRECT
worktree_root = "../worktree-pr-{number}"
file_path = f"{worktree_root}/.agents/sessions/session.md"

# WRONG - writes to main repo
file_path = ".agents/sessions/session.md"  # VIOLATION
```

### 4. Git Operations (MUST)

**Git commands MUST be executed from within the worktree directory.**

```bash
# CORRECT
cd ../worktree-pr-{number}
git add .
git commit -m "message"
git push

# WRONG - operates on main repo
git -C ../worktree-pr-{number} add .  # Risky - easy to forget -C flag
```

### 5. Verification Gate (MUST)

**Before cleanup, verify no files were written outside worktrees:**

```bash
# Check main repo for unexpected changes
cd {main_repo}
git status --short

# If output is non-empty, HALT and investigate
# Changes in main repo during parallel execution = constraint violation
```

## Prerequisites

1. **GitHub CLI**: `gh auth status` must show authenticated
2. **Git**: Push access to repository
3. **PowerShell**: Required for GitHub skill scripts
4. **pr-comment-responder skill** (optional): If you use the companion `pr-comment-responder` workflow for detailed single-PR review, ensure the skill is available (provided separately)

## Related Commands

- `pr-comment-responder` skill: Single PR detailed review (optional, provided separately)
- `/commit` - Commit changes with conventional format
- `/github` - GitHub CLI operations skill
