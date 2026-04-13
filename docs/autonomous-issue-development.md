# Autonomous Issue Development Prompt

Use this prompt to start an autonomous development session that continuously discovers, implements, and ships high-impact issues from the repository.

## Prompt

````text
You are an autonomous development agent responsible for identifying, implementing, and delivering high-impact work from a GitHub repository. Your goal is to continuously select priority issues, complete development work through a multi-agent workflow, and open pull requests until a target number is reached.

Here is the GitHub repository you will be working with: {{GITHUB_REPO_URL}}

Here is the assignee that all selected issues must be assigned to: {{TARGET_ASSIGNEE}}

Here is the target number of PRs to open: {{TARGET_PR_COUNT}}

Your workflow consists of the following phases that must be executed for each issue:

PHASE 1: ISSUE DISCOVERY AND PRIORITIZATION
- Navigate to the issues page at {{GITHUB_REPO_URL}}/issues
- Filter for issues with priority labels (priority:P0, priority:P1, priority:P2, etc.)
- Evaluate each priority-labeled issue for:
  - Return on Investment (ROI): Consider effort required vs. value delivered
  - Impact to project: Consider user benefit, technical debt reduction, security improvements, or feature completeness
- Select the single highest ROI/impact issue that is not already assigned or in progress

PHASE 2: ISSUE ASSIGNMENT AND BRANCH CREATION
- Assign the selected issue to {{TARGET_ASSIGNEE}}
- Create a new branch for the development work following the repository's branch naming conventions
- Document the issue number, title, and branch name for tracking

PHASE 3: DEVELOPMENT WORKFLOW
- Begin work using the orchestrator agent to coordinate development activities
- The orchestrator agent should plan the implementation approach and coordinate sub-tasks
- Implement the required changes to address the issue

PHASE 4: RECURSIVE REVIEW CYCLES
You must complete the following review cycles in order, and each must be performed recursively until all feedback is addressed:

a) Critic Review (Recursive):
   - Submit work to the critic agent for review
   - The critic evaluates completeness, correctness, and alignment with requirements
   - Address all critic feedback
   - Repeat until the critic approves with no further changes

b) QA Review (Recursive):
   - Submit work to the QA agent for testing and quality assurance
   - The QA agent evaluates functionality, edge cases, and test coverage
   - Address all QA feedback
   - Repeat until QA approves with no further issues

c) Security Review (Recursive):
   - Submit work to the security agent for security analysis
   - The security agent evaluates vulnerabilities, security best practices, and compliance
   - Address all security feedback
   - Repeat until security approves with no concerns

PHASE 5: RETROSPECTIVE AND ARTIFACT MANAGEMENT
Before opening a PR, you must:
- Complete a retrospective documenting:
  - What went well during the development process
  - What could be improved
  - Lessons learned
  - Time spent in each phase
- Generate and collect all artifacts including:
  - Code changes
  - Test results
  - Review feedback and responses
  - Retrospective document
- Commit all artifacts to the branch
- Push the branch to the remote repository

PHASE 6: PR CREATION AND REVIEW
- Open a new pull request from your branch to the main branch
- Ensure the PR description references the issue number and summarizes the changes
- After the PR is opened, execute the command: /pr-review <PR_NUM> where <PR_NUM> is the pull request number
- Monitor for and resolve any comments from the PR review
- Follow the protocol documented at: {{GITHUB_REPO_URL}}/blob/main/docs/autonomous-pr-monitor.md

CONTINUOUS LOOP BEHAVIOR
After completing all phases for one issue and opening its PR, immediately begin again at Phase 1 to select the next highest priority issue. Continue this loop until you have opened {{TARGET_PR_COUNT}} new pull requests.

For each iteration, use the scratchpad to:
- Track which issues you've already processed
- Count how many PRs you've opened so far
- Plan your next actions
- Document any blockers or issues encountered

Your output for each iteration should include:
1. The scratchpad showing your planning and tracking
2. A summary of actions taken in each phase
3. The PR number and URL for the newly created pull request
4. A count of total PRs opened so far vs. target

Use this space to:
- List issues you're evaluating and their priority/impact scores
- Track which issue you selected and why
- Note the branch name created
- Track review cycles and feedback
- Count PRs opened (X of {{TARGET_PR_COUNT}})
- Plan next steps

After your scratchpad, provide a structured summary of the work completed. Your final output should clearly indicate:
- Which issue was addressed (number and title)
- The branch name created
- Summary of changes made
- Results from each review cycle (critic, QA, security)
- Key points from the retrospective
- The PR number and URL
- Current progress toward the target ({{TARGET_PR_COUNT}} PRs)

Continue the loop automatically until {{TARGET_PR_COUNT}} PRs have been opened.
````

## What This Prompt Does

The agent will:

1. **Discover high-impact issues** - Scan the repository for priority-labeled issues (P0, P1, P2) and evaluate them for ROI and impact

2. **Prioritize by value** - Select issues that maximize value delivery while minimizing effort:
   - User benefit and feature completeness
   - Technical debt reduction
   - Security improvements
   - Bug fixes affecting users

3. **Execute multi-agent workflow** - Coordinate specialized agents for each phase:
   - **Orchestrator**: Plans and coordinates the implementation
   - **Implementer**: Writes production-quality code
   - **Critic**: Validates completeness and correctness
   - **QA**: Tests functionality and edge cases
   - **Security**: Reviews for vulnerabilities

4. **Complete recursive reviews** - Each review agent provides feedback that must be fully addressed before proceeding

5. **Generate artifacts** - Create retrospectives, test results, and documentation

6. **Open PRs automatically** - Create pull requests with proper issue references and trigger PR review workflows

## Workflow Phases

| Phase | Description | Agent(s) | Output |
|-------|-------------|----------|--------|
| 1. Discovery | Find and prioritize issues | - | Selected issue |
| 2. Assignment | Assign issue, create branch | - | Branch name |
| 3. Development | Implement the solution | Orchestrator, Implementer | Code changes |
| 4a. Critic Review | Validate completeness | Critic | Approval or feedback |
| 4b. QA Review | Test functionality | QA | Approval or feedback |
| 4c. Security Review | Check vulnerabilities | Security | Approval or feedback |
| 5. Retrospective | Document learnings | Retrospective | Retrospective doc |
| 6. PR Creation | Open and review PR | - | PR URL |

## Common Development Patterns

These patterns were validated during autonomous development sessions and have high success rates.

### Pattern 1: Branch Already Exists

**Problem**: Creating a branch fails because it already exists from a previous attempt.

```bash
# WRONG - Fails if branch exists
git checkout -b feat/123-feature

# CORRECT - Check and handle existing branch
git branch -D feat/123-feature 2>/dev/null || true
git checkout -b feat/123-feature
```

### Pattern 2: Issue Already Has PR

**Problem**: Selected issue already has an open or merged PR.

```bash
# CHECK BEFORE STARTING WORK
gh pr list --search "{number} in:title" --state all --json number,state

# If PR exists:
# - OPEN: Skip this issue, select next priority
# - MERGED: Close issue if still open, select next priority
# - CLOSED: Evaluate if work should continue
```

### Pattern 3: Test Module Import Failures

**Problem**: Tests fail because module paths are incorrect.

```powershell
# WRONG - Assumes test is in same directory as module
$ModulePath = Join-Path $PSScriptRoot "modules" "GitHubHelpers.psm1"

# CORRECT - Navigate from test location to module location
# From: .github/tests/skills/github/
# To:   .claude/skills/github/modules/
$ModulePath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "modules" "GitHubHelpers.psm1"
```

### Pattern 4: Markdown Lint Violations

**Problem**: Generated documentation fails markdownlint checks.

```bash
# ALWAYS run before commit
npx markdownlint-cli2 --fix "**/*.md"

# Common fixes applied automatically:
# - MD009: Trailing spaces
# - MD012: Multiple consecutive blank lines
# - MD022: Headings should be surrounded by blank lines
# - MD032: Lists should be surrounded by blank lines
```

### Pattern 5: Review Cycle Timeout

**Problem**: Review agent provides feedback but approval not reached after 3+ cycles.

```text
# Escalation protocol:
1. After 3 cycles without approval, document remaining issues
2. Create PR with "WIP:" prefix and link to blocking feedback
3. Add "blocked" label and assign to human reviewer
4. Move to next issue in queue
```

## Key Commands Used

**Note**: Replace placeholders with actual values:

- `{{GITHUB_REPO_URL}}` - Your repository URL (e.g., `https://github.com/owner/repo`)
- `{{TARGET_ASSIGNEE}}` - Bot or user to assign issues to (e.g., `rjmurillo-bot`)
- `{{TARGET_PR_COUNT}}` - Number of PRs to open (e.g., `5`)
- `{number}` - Issue or PR number

```bash
# List priority issues
gh issue list --state open --label "priority:P0" --json number,title,assignees
gh issue list --state open --label "priority:P1" --json number,title,assignees
gh issue list --state open --label "priority:P2" --json number,title,assignees

# Assign issue to bot
gh issue edit {number} --add-assignee {{TARGET_ASSIGNEE}}

# Create feature branch
git checkout -b feat/{number}-description

# Check for existing PRs on an issue
gh pr list --search "{number} in:title" --state all --json number,title,state

# Create PR referencing issue
# DANGER: If the PR title is constructed from untrusted input (like a GitHub issue title),
# it can lead to command injection if it contains shell metacharacters like `$(...)`.
# Use `read -r` to safely read the title into a variable.
read -r pr_title < <(gh issue view {number} --json title --jq -r .title)
gh pr create --title "feat: ${pr_title}" --body "Fixes #{number}"

# Run PR review after creation
/pr-review {pr_number}
```

## Example Session Output

The agent tracks progress using TodoWrite and provides structured output for each iteration.

### TodoWrite Task Tracking

```text
[1. [completed] ITERATION 3: Discover and prioritize issues]
[2. [completed] ITERATION 3: Selected Issue #549 - Set-IssueLabels parsing error]
[3. [completed] ITERATION 3: Create branch fix/549-set-issue-labels-parsing]
[4. [completed] ITERATION 3: Implement fix (change #$Issue: to #${Issue}:)]
[5. [completed] ITERATION 3: Critic review - APPROVED]
[6. [completed] ITERATION 3: QA review - APPROVED (added test case)]
[7. [completed] ITERATION 3: Security review - APPROVED]
[8. [in_progress] ITERATION 3: Create PR and run /pr-review]
[9. [pending] ITERATION 4: Start next issue]
```

### Scratchpad Example

```text
## SCRATCHPAD - Iteration 3

**Target**: 5 PRs | **Opened**: 2 | **Remaining**: 3

### Phase 1: Issue Discovery
| Issue | Priority | Effort | Impact | Status |
|-------|----------|--------|--------|--------|
| #549 | P2 | Low | High | SELECTED |
| #551 | P1 | Medium | High | Skipped (already assigned) |
| #506 | P2 | Low | Medium | Next candidate |

**Selection rationale**: #549 is a simple parsing bug fix (1 line change)
that unblocks the Set-IssueLabels skill for all users.

### Phase 2: Assignment
- Issue: #549 - Set-IssueLabels.ps1 parsing error
- Branch: fix/549-set-issue-labels-parsing
- Assignee: rjmurillo-bot

### Phase 3: Development
Agent delegation: Task(subagent_type="implementer", prompt="Fix parsing error...")
Implementation: Changed line 112 from `#$Issue:` to `#${Issue}:`

### Phase 4: Review Cycles

**Critic Review (Cycle 1)**:
- Feedback: None - fix is correct and complete
- Status: APPROVED

**QA Review (Cycle 1)**:
- Feedback: "Add test case for colon in output string"
- Status: REQUEST CHANGES

**QA Review (Cycle 2)**:
- Added test: `It "Handles colon after variable in output" { ... }`
- Status: APPROVED

**Security Review (Cycle 1)**:
- Feedback: No security implications for string formatting fix
- Status: APPROVED

### Phase 5: Retrospective
- What went well: Simple fix identified quickly, minimal code change
- What could improve: Should have caught this in original PR review
- Learning: PowerShell variable scoping with colons requires ${} delimiter

### Phase 6: PR Created
- PR #552: fix(skill): escape variable in Set-IssueLabels.ps1 string
- URL: https://github.com/owner/repo/pull/552
- Status: /pr-review 552 executed

**Progress: 3 of 5 PRs opened**
```

### Agent Handoff Messages

```text
[orchestrator → implementer]: "Implement fix for issue #549. The bug is on line 112
where $Issue: is parsed as a scope modifier. Change to ${Issue}:"

[implementer → critic]: "Fix complete. Changed #$Issue: to #${Issue}: on line 112.
Commit: c827d99. Ready for review."

[critic → qa]: "Implementation approved. Code change is minimal and correct.
Proceeding to QA review."

[qa → security]: "Functional testing complete after adding test case.
No edge cases identified. Proceeding to security review."

[security → orchestrator]: "No security implications. Fix approved.
Ready for PR creation."
```

## Agent Responsibilities

| Agent | Responsibility | Review Focus |
|-------|---------------|--------------|
| **Orchestrator** | Coordinates workflow, routes to specialists | Task breakdown, sequencing |
| **Implementer** | Writes code following project patterns | SOLID principles, clean code |
| **Critic** | Validates plan completeness | Requirements alignment, gaps |
| **QA** | Tests functionality | Edge cases, test coverage |
| **Security** | Reviews for vulnerabilities | OWASP, secure coding |
| **Retrospective** | Extracts learnings | What worked, what didn't |

## Troubleshooting

### Issue Already Assigned

**Detection**: `gh issue view {number} --json assignees` returns non-empty assignees array.

**Resolution**:

1. Check if assignee is `{{TARGET_ASSIGNEE}}` - if yes, check for existing PR
2. If assigned to different user/bot - skip and select next priority issue
3. If PR exists but is closed without merge - evaluate if work should continue

### Review Cycle Deadlock (3+ Iterations)

**Detection**: Same feedback received 3 times without resolution.

**Resolution**:

1. Document the blocking feedback in the PR description
2. Add `blocked` label to the issue
3. Create a WIP PR with current progress
4. Post comment requesting human review
5. Move to next issue in queue

### Branch Conflicts During PR Creation

**Detection**: `gh pr create` fails with merge conflict error.

**Resolution**:

```bash
# Update branch with latest main
git fetch origin main
git merge origin/main --no-edit

# If conflicts exist:
# 1. Resolve conflicts in affected files
# 2. For HANDOFF.md conflicts, use --theirs (per ADR-014)
git checkout --theirs .agents/HANDOFF.md

# Complete merge and push
git add .
git commit -m "chore: resolve merge conflicts"
git push
```

### API Rate Limiting

**Detection**: `gh` commands fail with 403 or rate limit error.

**Resolution**:

1. Check rate limit: `gh api rate_limit --jq '.rate'`
2. If exhausted, wait for reset (shown in response)
3. Consider using `GH_TOKEN` with higher rate limit
4. Batch operations to reduce API calls

### Session Protocol Validation Failures

**Detection**: Pre-commit hook blocks commit with validation error.

**Resolution**:

1. Run `pwsh scripts/Validate-SessionEnd.ps1 -SessionLogPath ".agents/sessions/[log].md"`
2. Address each validation error (QA report, evidence, etc.)
3. For documentation-only changes, ensure no code file patterns detected
4. If false positive, document justification and use `--no-verify` with explanation

## Prerequisites

- GitHub CLI (`gh`) authenticated with appropriate permissions
- Git configured with push access to feature branches
- Multi-agent system configured (see `AGENTS.md`)
- Session protocol compliance (see `.agents/SESSION-PROTOCOL.md`)
- Access to create and assign issues
- Access to create pull requests

## Related Documentation

- [Autonomous PR Monitor](./autonomous-pr-monitor.md) - Monitoring and fixing open PRs
- [AGENTS.md](../AGENTS.md) - Agent system documentation
- [SESSION-PROTOCOL.md](../.agents/SESSION-PROTOCOL.md) - Session requirements
