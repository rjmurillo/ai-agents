# MANDATORY: Use Claude Skills, Never Raw Commands

**Importance**: **CRITICAL**
**Date**: 2025-12-18
**Applies To**: ALL agents

## The Rule

**NEVER use raw commands when a Claude skill exists for that functionality.**

Specifically:

### GitHub Operations

WRONG: `gh pr view`, `gh issue create`, `gh api ...`
CORRECT: Use `.claude/skills/github/` scripts

**Why**: Skills are tested, handle errors, have proper parameter validation, and are maintained centrally.

### Examples

#### Creating Issues

WRONG:

```bash
gh issue create --title "..." --body "..." --label "enhancement"
```

CORRECT:

```powershell
# Check .claude/skills/github/scripts/issue/ for available scripts
# If capability missing, ADD to skill, don't write inline
```

#### Posting PR Comments

WRONG:

```bash
gh pr comment $PR_NUMBER --body "$COMMENT"
```

CORRECT:

```powershell
& .claude/skills/github/scripts/pr/Post-PRCommentReply.ps1 -PullRequest $PR_NUMBER -Body $COMMENT
```

#### Getting PR Context

WRONG:

```bash
gh pr view $PR_NUMBER --json title,body,files
```

CORRECT:

```powershell
& .claude/skills/github/scripts/pr/Get-PRContext.ps1 -PullRequest $PR_NUMBER -IncludeChangedFiles
```

## Root Cause of Violations

**Why agents keep using raw `gh`**:

1. **Habit**: Default to inline bash/PowerShell scripts
2. **Not checking first**: Don't verify if skill exists before writing code
3. **Ignoring user corrections**: Pattern repeats despite feedback
4. **Lack of discipline**: Even after being corrected, reverting to old patterns

## The Process

### Before Writing ANY GitHub Operation:

1. **CHECK**: Does `.claude/skills/github/` have this capability?

   ```powershell
   ls .claude/skills/github/scripts/**/*.ps1
   ```

2. **USE**: If exists, use the skill script

3. **EXTEND**: If missing, add to skill (don't write inline)
   - Create new script in appropriate directory (pr/, issue/, reactions/)
   - Add Pester tests
   - Update skill documentation
   - Then use it

### This Applies To:

- GitHub operations (`gh` command)
- File operations (if skill exists)
- Any operation where a tested, validated skill exists

### This Does NOT Apply To:

- Git operations (`git` commands) - no skill for this yet
- Build operations (npm, pwsh for build scripts)
- System operations (ls, mkdir, etc.)

## Enforcement

**User will reject PRs/commits that:**

- Use raw `gh` commands when skill exists
- Write inline scripts duplicating skill functionality
- Ignore this guidance after being corrected

## Skill Location

```text
.claude/skills/github/
|-- SKILL.md (documentation)
|-- modules/
|   `-- GitHubHelpers.psm1 (shared functions)
|-- scripts/
|   |-- pr/
|   |   |-- Get-PRContext.ps1
|   |   |-- Post-PRCommentReply.ps1
|   |   |-- Get-PRReviewComments.ps1
|   |   `-- Get-PRReviewers.ps1
|   |-- issue/
|   |   |-- Get-IssueContext.ps1
|   |   |-- Post-IssueComment.ps1
|   |   |-- Set-IssueLabels.ps1
|   |   `-- Set-IssueMilestone.ps1
|   `-- reactions/
|       `-- Add-CommentReaction.ps1
`-- tests/
    `-- GitHubHelpers.Tests.ps1
```

## Before Every GitHub Operation

**Ask yourself**:

1. Is this a GitHub operation? (PR, issue, comment, label, etc.)
2. Does `.claude/skills/github/` have this? (CHECK FIRST!)
3. If yes -> Use skill
4. If no -> Add to skill, THEN use it

**DO NOT** write raw `gh` commands inline. Ever.

## Related

- ADR-005: PowerShell-only scripting
- ADR-006: Thin workflows, testable modules
- User preference: No bash/Python (use `mcp__serena__read_memory` with `memory_file_name="user-preference-no-bash-python"`)
- Pattern: Thin workflows (use `mcp__serena__read_memory` with `memory_file_name="pattern-thin-workflows"`)
