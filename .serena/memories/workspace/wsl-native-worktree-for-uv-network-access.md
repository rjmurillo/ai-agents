# Prefer a native WSL worktree for uv-dependent work

In this environment, a Windows-native git worktree can fail `uv` and `pip`
resolution with TLS handshake errors while the same repository works from a
native WSL path. For `uv run`, `uv sync`, or mutation-harness work in this
repository, start from a WSL-native worktree under `/home/<user>/...`, not
under `/mnt/c/...`.

## Why

PR #5344 hit repeated Windows-only failures:

- `uv sync` and `uv run` failed with network handshake errors.
- A partial `uv` install left no usable `uv` binary on PATH.
- The same commands succeeded after rebuilding the worktree under WSL with a
  real `uv` install.

## Practice

1. Create the worktree under a native Linux path.
2. Confirm `command -v uv` before running the test or build.
3. Move to WSL immediately if a Windows worktree shows TLS handshake failures.

## Evidence

- PR `rjmurillo/ai-agents#5344`
- Retrospective `2026-09-01-pr5344-mutation-harness-zero-collection.md`
