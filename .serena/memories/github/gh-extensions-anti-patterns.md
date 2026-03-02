# GitHub CLI Extension Anti-Patterns

Avoid these common mistakes when using GitHub CLI extensions in agent workflows.

## Anti-Pattern-Ext-001: Using Interactive Mode

**Problem**: Running extensions without required flags launches interactive TUI.

**Solution**: Always use required flags to avoid prompts:

| Extension | Required Flag |
|-----------|--------------|
| gh-notify | `-s` (static mode) |
| gh-hook | `--file` (from JSON) |
| gh-milestone | `--title` (create) |
| gh-sub-issue | `--parent --title` (create) |

## Anti-Pattern-Ext-002: gh-grep Without Include Filter

**Problem**: `gh grep` without `--include` is extremely slow.

**Solution**: Always specify `--include "*.extension"` to filter file types.

```bash
# BAD - Very slow
gh grep "TODO" --repo owner/repo

# GOOD - Fast
gh grep "TODO" --repo owner/repo --include "*.js"
```

## Anti-Pattern-Ext-003: Forgetting Merge Commit for Combined PRs

**Problem**: Squash merging a combined PR leaves original PRs open.

**Solution**: Always use **Merge Commit** when merging combined PRs from `gh combine-prs`.

This ensures GitHub correctly marks all original PRs as "Merged" rather than "Closed".

## Related

- [gh-extensions-combine-prs](gh-extensions-combine-prs.md)
- [gh-extensions-grep](gh-extensions-grep.md)
- [gh-extensions-hook](gh-extensions-hook.md)
- [gh-extensions-maintenance](gh-extensions-maintenance.md)
- [gh-extensions-metrics](gh-extensions-metrics.md)
