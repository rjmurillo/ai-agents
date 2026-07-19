# Lefthook Migration Contracts

As of branch `chore/lefthook-migration` (2026-07-19), OSS Lefthook 2.1.10 is the repository's only local Git hook manager.

## Canonical paths

- Configuration: `lefthook.yml`
- Payloads: `scripts/hooks/pre-commit`, `scripts/hooks/commit-msg`, `scripts/hooks/pre-push`
- The legacy `.githooks` directory and `scripts/install_git_hooks.py` are removed.

## Installation

Lefthook is pinned through the `dev` dependency set in `pyproject.toml` and `uv.lock`.

```bash
uv sync --frozen --extra dev
uv run --frozen --extra dev lefthook install --reset-hooks-path
uv run --frozen --extra dev lefthook check-install
```

`--reset-hooks-path` is required to migrate clones that still have `core.hooksPath=.githooks`. Linked worktrees use the installed Lefthook shims correctly.

## Runtime contracts

- `commit-msg` receives the message path through `{1}`.
- `pre-push` requires `use_stdin: true`; multi-ref and deletion-ref input is forwarded byte-for-byte.
- Lefthook normalizes nonzero payload exits to its own failure exit while preserving blocking behavior and payload output.
- Payload scripts retain their own staged-file, restaging, environment-control, warning, and fail-closed policies. Do not add Lefthook globs, broad restaging, or parallel execution around them.

## Security classification

Pinned Lefthook 2.1.10 auto-discovers 30 primary/local names from these factors:

- Bases: `lefthook`, `.lefthook`, `.config/lefthook`
- Suffixes: empty and `-local`
- Extensions: `.yml`, `.yaml`, `.json`, `.jsonc`, `.toml`

All 30 names are classified as security-sensitive across the commit gate, pre-commit security scan, and infrastructure risk detector. Arbitrary `LEFTHOOK_CONFIG` and `extends` targets are not pathname-auto-discovery surfaces.

## Validation

Use `lefthook validate`, `lefthook check-install`, `tests/test_lefthook_integration.py`, `tests/hooks`, `build/scripts/build_all.py --check`, `scripts/validation/pre_pr.py`, and `build/scripts/validate_plugin_version_bump.py --base origin/main`.

## Process learning

Never clean scratch paths by basename inside a repository. Use an absolute temporary directory, verify ownership, and refuse deletion when the resolved path is inside a repository or registered worktree. A QA cleanup accidentally deleted a sibling worktree and restored tracked files, but any prior untracked or ignored files could not be proven recoverable.