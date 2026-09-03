# Use a native WSL clone and worktree when Windows hits uv TLS failures

In this environment, a Windows-native git worktree can fail `uv` and `pip`
resolution with TLS handshake errors while the same repository works from a
native WSL path. When that failure reproduces, move `uv run`, `uv sync`, or
mutation-harness work for this repository into a WSL-native clone under
`/home/<user>/...` instead of continuing under `/mnt/c/...`.

## Why

PR #5344 hit repeated Windows-only failures:

- `uv sync` and `uv run` failed with network handshake errors.
- A partial `uv` install left no usable `uv` binary on PATH.
- The same commands succeeded after rebuilding the worktree under WSL with a
  real `uv` install.

## Practice

1. Reproduce the TLS handshake failure on the Windows-native worktree first.
2. Confirm `command -v uv` before running the test or build.
3. Create or refresh a native WSL clone under `/home/<user>/...`.
4. Add a worktree from that native clone and run the failing `uv` command there.
5. Do not rely on `git worktree move` from `/mnt/c/...` into WSL. A linked
   worktree still points at the original common `.git` directory, so moving
   only the checkout path leaves Git metadata and object access on the
   Windows-mounted filesystem that triggered the failure.

## Evidence

- PR `rjmurillo/ai-agents#5344`
- Retrospective `2026-09-01-pr5344-mutation-harness-zero-collection.md`
