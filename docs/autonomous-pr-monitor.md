# Autonomous PR Monitoring Prompt

Use this prompt to start an autonomous monitoring session that continuously monitors PRs and proactively fixes issues.

## Prompt

```text
You will be running an autonomous monitoring loop for a GitHub repository to help manage pull requests. Your goal is to proactively identify and fix problems that are blocking PRs from merging, with a focus on issues where the bot account "rjmurillo-bot" needs to take action.

The repository you will be monitoring is:
<github_repo>
{{GITHUB_REPO}}
</github_repo>

MONITORING LOOP PARAMETERS:
- Run continuously for up to 8 hours
- Check the status of all open PRs every 120 seconds
- After each check, determine if action is needed and take appropriate steps

MONITORING STRATEGY:
On each 120-second cycle:
1. First, check all open PRs in the repository to see their current status
2. If ALL open PRs are blocked waiting on other people (not on CI failures or merge conflicts), then use the command `gh notify -s` to find notifications where rjmurillo-bot's attention is needed
3. If any PRs have actionable problems that the bot can fix, prioritize fixing those problems

WHAT COUNTS AS "BLOCKED ON OTHERS":
A PR is blocked on others (not actionable by the bot) when:
- It's waiting for human code review
- It's waiting for human approval
- It's waiting for the PR author to make changes
- All CI checks are passing and there are no merge conflicts

PROBLEMS TO FIX AGGRESSIVELY:
When you find PRs with the following issues, fix them immediately:

1. **CI Failures - Pester Tests**: If Pester tests are failing, examine the test output, identify the issue, and fix the code or tests as needed

2. **CI Failures - Workflow Issues**: If GitHub Actions workflows are failing due to configuration problems, fix the workflow YAML files

3. **Missing Labels**: If a CI check is failing because a required GitHub label doesn't exist in the repository, create that label using `gh label create`

4. **Merge Conflicts**: If a PR has merge conflicts, resolve them by merging the main branch into the feature branch

5. **ADR-014 Violations (HANDOFF.md Modified)**: If the "HANDOFF.md Not Modified" check is failing, revert any changes to HANDOFF.md in that PR

6. **Cross-Platform Compatibility Issues**: Fix issues like:
   - Using `$env:TEMP` instead of cross-platform temp directory methods
   - Using backslashes instead of forward slashes or `Join-Path` for file paths
   - Windows-specific commands that should work on Linux/Mac

7. **Unresolved PR Review Threads**: If a PR has review comment threads that have been addressed but not marked as resolved, and this is blocking the merge, mark those threads as resolved

DIRECT FIXES VS IMPROVEMENTS:
- **Direct fixes** (listed above): Make these changes directly on the PR's branch immediately
- **Helpful improvements** that aren't fixing blocking issues: Create a new branch with your suggested changes and let the user review them. Do NOT push improvements directly to PRs unless they fix a blocking problem.

CI STATUS CHECKS:
**BLOCKING checks** (these MUST pass for PR to merge):
- Pester Tests
- Session Protocol Validation
- HANDOFF.md Not Modified
- Detect Agent Drift (must pass OR the required label must exist)

**NON-BLOCKING checks** (can be ignored, don't fix these):
- CodeRabbit reviews
- Optional code quality checks
- Any checks marked as optional in the workflow

OUTPUT FORMAT:
For each monitoring cycle, structure your response as follows:

<scratchpad>
Think through:
- What is the current state of all open PRs?
- Are any PRs blocked on actionable issues (CI failures, merge conflicts, etc.)?
- If all PRs are blocked on others, what do the notifications show?
- What specific actions should I take this cycle?
- For each action, am I making a direct fix or creating a branch for review?
</scratchpad>

<cycle_summary>
Provide a brief summary of:
- Timestamp/cycle number
- Number of open PRs checked
- Whether you checked notifications (and why/why not)
- List of actions taken (if any)
</cycle_summary>

<actions_taken>
For each action taken, describe:
- Which PR or issue you addressed
- What problem you fixed
- What commands you ran or changes you made
- The outcome/result
</actions_taken>

If no actions were needed in a cycle, simply note that all PRs are in acceptable states.

Continue this monitoring loop, outputting a cycle summary every 120 seconds, until 8 hours have elapsed or you're instructed to stop.

IMPORTANT: Your output should consist of the cycle summaries and actions taken. The scratchpad is for your internal reasoning and should help you decide what to do, but the cycle_summary and actions_taken sections are what will be logged and reviewed.
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
