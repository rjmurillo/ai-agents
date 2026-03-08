---
description: Use when checking a PR description for conventional commit format, issue keywords, and template compliance before submission
allowed-tools:
  - Bash(python3 .claude/skills/github/scripts/pr/test_pr_description.py:*)
---

# Validate PR Description Command

## Context

- PR title: [User provides]
- PR body file: [User provides path or content]

## Your task

Validate the PR description using the test_pr_description skill:

```bash
python3 .claude/skills/github/scripts/pr/test_pr_description.py \
  --title "[title]" \
  --body-file "[path-to-body.md]"
```

Review the validation output and report:

1. Conventional commit title compliance
2. GitHub keyword presence (Closes/Fixes/Resolves)
3. PR template section completion
4. Any warnings or errors

Provide actionable recommendations for any validation failures.
