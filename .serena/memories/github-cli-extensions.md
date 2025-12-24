# GitHub CLI Extensions

## Skill-GH-Extension-001: Extension Management (92%)

**Statement**: Use `gh extension` to install community tools; extensions are repos with `gh-` prefix.

```bash
# Search and install
gh extension search copilot
gh extension install github/gh-copilot

# Upgrade all
gh extension upgrade --all

# Remove
gh extension remove extension-name
```

**Directory**: <https://github.com/topics/gh-extension>

## Recommended Extensions

### gh-dash: Interactive PR/Issue Dashboard (94%)

```bash
gh extension install dlvhdr/gh-dash
gh dash  # Launch TUI
```

**Keys**: `j/k` navigate, `Enter` view, `d` diff, `c` checkout, `m` merge

### gh-combine-prs: Batch Dependabot PRs (93%)

```bash
gh extension install rnorth/gh-combine-prs
gh combine-prs --query "author:app/dependabot"
```

**Important**: Use Merge Commit (not squash) so GitHub marks originals as merged.

### gh-notify: Notification Management (92%)

```bash
gh extension install meiji163/gh-notify
gh notify  # Interactive (requires fzf)
gh notify -e "dependabot"  # Exclude pattern
```

### gh-milestone: Milestone Management (93%)

```bash
gh extension install valeriobelli/gh-milestone
gh milestone create --title "v2.0.0" --due-date 2025-03-01
gh milestone list
```

### gh-metrics: PR Analytics (91%)

```bash
gh extension install hectcastro/gh-metrics
gh metrics --repo owner/repo --start 2025-01-01 --end 2025-01-31
```

Calculates: Time to First Review, Feature Lead Time, First to Last Review.

### gh-gr: Multi-Repository Operations (90%)

```bash
gh extension install sarumaj/gh-gr
gh gr init -d ~/projects
gh gr pull  # Pull all repos
gh gr status  # Status of all
```

### gh-grep: Cross-Repository Search (88%)

```bash
gh extension install k1LoW/gh-grep
gh grep "TODO" --owner myorg --include "*.go"
```

**Warning**: Slow - uses GitHub API. Always use `--include` to filter.

## Skill-GH-Extension-002: Sub-Issue Management (90%)

```bash
gh extension install yahsan2/gh-sub-issue
gh sub-issue create --parent 123 --title "Sub-task"
gh sub-issue list 123
```

**Note**: GitHub supports up to 8 levels of issue hierarchy via Tasklists.
