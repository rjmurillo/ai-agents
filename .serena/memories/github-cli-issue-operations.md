# GitHub CLI Issue Operations

## Skill-GH-Issue-001: Issue Creation (94%)

**Statement**: Use `gh issue create` with `--label`, `--assignee`, `--project`; `@me` for self-assignment.

```bash
# Full creation with metadata
gh issue create \
  --title "Bug: Login fails on Safari" \
  --body "## Steps to Reproduce\n\n1. Open Safari\n2. Click Login" \
  --label "bug,high-priority" \
  --assignee "@me" \
  --milestone "v2.0"

# Use template
gh issue create --template "Bug Report"
```

## Skill-GH-Issue-002: Issue Editing (93%)

**Statement**: Use `gh issue edit` for bulk operations; supports multiple issues and incremental changes.

```bash
# Add labels (preserves existing)
gh issue edit 23 --add-label "bug,help-wanted"

# Change assignees
gh issue edit 23 --add-assignee "@me" --remove-assignee olduser

# Edit multiple issues at once
gh issue edit 23 34 45 --add-label "needs-triage"

# Body from file
gh issue edit 23 --body-file updated-description.md
```

**Note**: Adding labels to projects requires `gh auth refresh -s project`.

## Skill-GH-Issue-003: Issue Lifecycle (91%)

**Statement**: Use `gh issue close`, `reopen`, `lock` for lifecycle management.

```bash
# Close with comment
gh issue close 23 -c "Fixed in PR #45"

# Close as not planned
gh issue close 23 -r "not planned"

# Transfer to another repo
gh issue transfer 23 owner/other-repo
```

## Skill-GH-Copilot-001: GitHub Copilot Assignment (98%)

**Statement**: Assign issues to `copilot-swe-agent` (exact name) to trigger Copilot automated resolution.

```bash
# CORRECT: Trigger Copilot with exact assignee name
gh issue edit 90 --add-assignee copilot-swe-agent

# WRONG: These do NOT trigger Copilot
gh issue comment 90 --body "@copilot please analyze"  # Mentions add context but don't assign
gh issue edit 90 --add-assignee Copilot               # Error: 'Copilot' not found
gh issue edit 90 --add-assignee copilot               # Error: 'copilot' not found
```

**Context Injection Pattern**:

```bash
# Step 1: Post context-rich comment mentioning @copilot
gh issue comment 90 --body "@copilot Use Option 1. Focus on the Apply Labels step."

# Step 2: Assign Copilot (this triggers work)
gh issue edit 90 --add-assignee copilot-swe-agent
```

When Copilot is assigned, it reads ALL comments where @copilot is mentioned.

**Evidence**: Issues #88, #90
