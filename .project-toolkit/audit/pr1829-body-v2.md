## Summary

The on-edit markdown lint hook hangs the editor for 2-3 minutes on every Write/Edit of a `.md` file. Root cause: `.markdownlint-cli2.yaml` declares a top-level `globs:` block; `markdownlint-cli2` adds config globs to argv-supplied paths, so a single-file invocation lints the touched file plus every markdown file matched by the config globs.

This PR removes the `globs:` block (single-file callers now lint only the named file) and hardens `ignores:` so the full-repo walk no longer recurses through caches, worktree mirrors, and provider state directories.

## Files

- `.markdownlint-cli2.yaml`

## Measured impact

| Invocation | Before | After | Speedup |
|---|---|---|---|
| Single-file (the on-edit hook) | 2:53 min | 0.747 s | 231x |
| Full-repo (the explicit canonical caller) | 6:19.70 min, 373,381 paths walked | 5.5 s, 696 markdown files | 68x |

## What stays the same

- All lint rules. No semantic changes to rule configuration.
- The 569 errors the full-repo run surfaces are pre-existing content findings; this change does not silence any of them.
- Full-repo invocations explicitly pass a glob (e.g. star-star slash star dot md) on the command line and continue to work.

## Test plan

- [x] Single-file lint returns in under 1 second and reports `Linting: 1 file(s)` (was: minutes, was linting the entire repo).
- [x] Full-repo lint returns in ~5 seconds and reports `Linting: 696 file(s)` (was: 6:19, 373,381 paths).
- [x] YAML config still parses.
- [ ] CI green.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
