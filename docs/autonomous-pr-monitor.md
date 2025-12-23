# Autonomous PR Monitoring Prompt

Use this prompt to start an autonomous monitoring session that continuously monitors PRs and proactively fixes issues.

## Prompt

```text
Run an autonomous monitoring loop indefinitely (up to 8 hours). Check PRs every 120 seconds.

When all PRs are blocked on others, use `gh notify -s` to find where rjmurillo-bot attention is needed.

Be aggressive at solving problems on PRs waiting on others:
- Fix CI failures when possible (Pester tests, workflow issues, missing labels)
- Resolve merge conflicts by merging main into feature branches
- Address ADR-014 violations (revert HANDOFF.md changes)
- Fix cross-platform compatibility issues ($env:TEMP, path separators)
- Create missing GitHub labels that workflows depend on
- Mark resolved PR review threads as resolved so PRs can merge

For helpful improvements that aren't direct fixes, put them in a new branch for user review.

CI Status Checks (BLOCKING conditions):
- Pester Tests must pass
- Session Protocol Validation must pass
- HANDOFF.md Not Modified must pass
- Detect Agent Drift must pass (or label must exist)

Non-blocking checks that can be ignored:
- CodeRabbit reviews
- Optional code quality checks
```

## What This Prompt Does

The agent will:

1. **Monitor PRs continuously** - Every 120 seconds, check all open PRs for:
   - Mergeable status
   - CI check status (distinguish between mergeable and actual CI pass)
   - Review comment status

2. **Fix CI failures** - Analyze and fix common issues:
   - PowerShell `$env:TEMP` should be `[System.IO.Path]::GetTempPath()` for cross-platform
   - Here-string terminators (`"@`) must start at column 0
   - Missing module installations in test setup (e.g., `powershell-yaml`)
   - Exit code issues in verification scripts (add `exit 0`)
   - Missing GitHub labels that workflows depend on

3. **Resolve merge conflicts** - For PRs with CONFLICTING status:
   - Checkout the worktree
   - Merge `origin/main` into the feature branch
   - Resolve conflicts (HANDOFF.md uses `--theirs` per ADR-014)
   - Push the resolved branch

4. **Enforce ADR-014** - HANDOFF.md is read-only on feature branches:
   - Revert any HANDOFF.md changes to match main
   - Ensure session context is preserved in session log files

5. **Create fix PRs** - For infrastructure issues that need broader fixes:
   - Create a feature branch
   - Apply the fix
   - Create a PR with clear summary

## Key Commands Used

```bash
# Check all PRs
gh pr list --state open --json number,title,headRefName,mergeable

# Check CI status for a specific PR
gh pr view {number} --json statusCheckRollup --jq '.statusCheckRollup[] | "\(.conclusion // .status)\t\(.name)"'

# Get failure logs
gh run view {run_id} --log-failed

# Create missing labels
gh api repos/{owner}/{repo}/labels -X POST -f name="label-name" -f description="..." -f color="..."

# Find notifications needing attention
gh notify -s
```

## Example Session Output

The agent tracks progress using TodoWrite:
- Check CI status on all PRs
- Fix PR #224 Pester test syntax error
- Fix PR #255 cross-platform temp path issue
- Create PR #298 for Copilot Workspace exit code fix
- Fixed PR #247 HANDOFF.md ADR-014 violation

## Prerequisites

- GitHub CLI (`gh`) authenticated
- Git worktrees set up for parallel PR work (`/home/richard/worktree-pr-{number}`)
- Access to push to feature branches
