# GitHub CLI PR Operations

## Skill-GH-PR-001: Pull Request Creation (95%)

**Statement**: Use `gh pr create` with explicit flags for automation; `--fill` for auto-population from commits.

```bash
# Automated creation with explicit values
gh pr create --base main --head feature-branch \
  --title "feat: add new feature" \
  --body "## Summary\n\nDescription here\n\nCloses #123"

# Auto-fill from commit messages
gh pr create --fill

# Create draft PR
gh pr create --draft --title "WIP: feature" --body "Work in progress"
```

## Skill-GH-PR-002: Pull Request Review (93%)

**Statement**: Use `gh pr review` with `-b` flag for body text; `-r` for request changes, `-a` for approve.

```bash
# Approve with comment
gh pr review --approve -b "LGTM! Great work."

# Request changes
gh pr review 123 -r -b "Please address the security concern"

# Leave comment (no approval/rejection)
gh pr review --comment -b "Have you considered..."
```

## Skill-GH-PR-003: Pull Request Merge (94%)

**Statement**: Use `gh pr merge` with `-s` for squash, `-d` for delete branch, `--auto` for auto-merge.

```bash
# Squash and delete branch (most common)
gh pr merge -sd

# Auto-merge when checks pass
gh pr merge --auto -sd

# Disable auto-merge
gh pr merge 123 --disable-auto
```

**Anti-pattern**: Forgetting `-d` leaves stale branches.

## Skill-GH-PR-004: Pull Request Listing (92%)

**Statement**: Use `gh pr list` with `--state`, `--label`, `--author` filters; `--json` for scripting.

```bash
# Filter by author
gh pr list --author @me

# JSON output for scripting
gh pr list --json number,title,author --jq '.[] | "\(.number): \(.title)"'

# List PRs needing review
gh pr list --search "review:required"
```

## Evidence

- GitHub CLI Manual
- Session 56 (2025-12-21)
