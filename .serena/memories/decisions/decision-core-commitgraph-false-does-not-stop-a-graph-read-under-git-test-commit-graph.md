# The core.commitGraph=false flag does not turn off the commit graph when GIT_TEST_COMMIT_GRAPH=1 is in the environment

**Atomicity**: 90%
**Category**: Git hook environment
**Source**: Agent session sweep, sessions dated 2026-07. Sweep ids E058. State checked on main at 1be533c496 (2026-11-26).

## Question

Does `git -c core.commitGraph=false` give trustworthy ancestry in a cleaned hook environment?

## Conventional answer

The `-c core.commitGraph=false` flag disables the commit graph. A cleaned environment then gives trustworthy ancestry.

## First-principles position

An strace of git 2.43 `rev-list` showed no commit-graph open with the flag alone. With `GIT_TEST_COMMIT_GRAPH=1` set, git opened the commit-graph file anyway. A second probe showed the environment cleaner also passed a `SEMGREP_URL` variable through to the subprocess. The flag is not enough when test variables survive in the environment.

## Evidence with limits

- The sweep inferred no commit graph open from the filtered trace for `git rev-list` with `-c core.commitGraph=false` alone (2026-07-19).
- With `GIT_TEST_COMMIT_GRAPH=1` set, git opened `.git/objects/info/commit-graph` anyway.
- A second probe showed `_clean_git_env()` passed `SEMGREP_URL` through to the subprocess.
- Quote: "openat(AT_FDCWD, ".git/objects/info/commit-graph", O_RDONLY|O_CLOEXEC) = 3 ... (strace of GIT_TEST_COMMIT_GRAPH=1 git -c core.commitGraph=false rev-list --count HEAD)"
- Limits: Single run, git 2.43.0, Linux, one repo, 2026-07-19. The transcript shows the open after the second strace, but it was not rerun. The first strace's empty output is inferred from the candidate's text and the grep filter.
- State on main at 1be533c496 (2026-11-26): fixed. `git_hook_policy.py:926` strips keys that start with `GIT_TEST_COMMIT_GRAPH` or `SEMGREP_`, and `:929` sets `GIT_TEST_COMMIT_GRAPH=0`.

## Decision

To bypass the commit graph, strip `GIT_TEST_COMMIT_GRAPH*` from the environment. Set `GIT_TEST_COMMIT_GRAPH=0` and also pass `-c core.commitGraph=false`. Strip `SEMGREP_` variables from hook subprocess environments.
