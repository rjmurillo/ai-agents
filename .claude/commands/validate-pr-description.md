---
description: Use when validating a PR title and description for conventional commit format, issue linking keywords, and template compliance before submission
allowed-tools:
  - Bash(python3:*)
  - Bash(git:*)
  - Read
  - Glob
  - Grep
---

# Validate PR Description Command

## Context

- PR title: [User provides]
- PR body: [User provides text or path to a file]

## Your task

Validate the PR description against these standards:

### 1. Conventional Commit Title

Title must match `<type>(<scope>)?: <description>` where type is one of:
`feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`, `build`, `revert`.

### 2. Issue Linking Keywords

Body should contain at least one issue linking keyword:
`Closes #N`, `Fixes #N`, `Resolves #N` (and their past-tense variants).
These keywords auto-close the linked issue when the PR merges on platforms that support them (GitHub, GitLab). On other platforms (Azure DevOps, Bitbucket), they serve as traceability markers.

### 3. PR Template Compliance

Check that required sections are populated:

- Summary (non-empty)
- Changes (at least one item)
- Type of Change (at least one checkbox marked)

### Validation Script (optional)

If `.claude/skills/github/scripts/pr/validate_pr_description.py` exists, run it:

```bash
python3 .claude/skills/github/scripts/pr/validate_pr_description.py \
  --title "[title]" \
  --body-file "[path-to-body.md]"
```

Otherwise, validate manually against the criteria above.

Report findings with actionable recommendations for any failures.
