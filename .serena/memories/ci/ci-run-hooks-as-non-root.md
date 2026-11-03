# Run hooks, tests, and pushes as a non-root user in managed containers

## Rule

In a managed cloud container (Claude Code on the web and similar), do not run
`git push`, the pre-push suite, or `pytest` as root. Run them as the
container's non-root user (`claude`, uid 999 in the 2026-11 image) from that
user's own clone, with a clean environment (`env -i` plus only the variables
the tools need). Root is not how contributors or CI run this repository, and
the pre-push gate cannot pass as root.

## What root broke (measured 2026-10-31 to 2026-11-03)

- **Permission tests.** `tests/eval/test_cli_credentials.py::test_an_unreadable_regular_file_reads_as_not_found`
  and the `test_check_git_hook_health*.py` tests failed as root because root
  can read a mode-000 file. All passed as `claude`.
- **Leaked session environment.** Root's shell exports `GH_TOKEN` and
  `PYTHONUNBUFFERED`. The three `test_cli_credential_transports.py` Copilot
  tests and `test_pre_pr_console.py::TestEnableLineBuffering` failed until the
  run used `env -i`.
- **testmon reran everything.** Root's interpreter carries extra packages, so
  testmon reported "packages installed ... have been changed" and selected the
  whole suite, which cannot finish inside the pre-push pytest budget (180s).
  A fresh `uv sync --frozen --extra dev` venv owned by `claude` does not.
- **Stale mutation marker.** A full-suite run killed mid-way left
  `.git/mutation-active/<id>.json`. `mutation_workspace recover` then refused,
  because the branch had moved and the recorded target hash no longer matched.
  A fresh clone has no marker.

## Recipe

1. Make the toolchain readable: copy `uv` to `/usr/local/bin`, copy uv's
   managed Python to a shared directory and set `UV_PYTHON_INSTALL_DIR` to it
   with `UV_PYTHON_DOWNLOADS=never`, and copy the proxy CA bundle out of
   `/root` (mode 700) to a world-readable path.
2. As `claude`, clone from GitHub, not from root's checkout. git refuses a
   root-owned repository ("dubious ownership"). Move unpushed commits with
   `git bundle`.
3. Run the CONTRIBUTING.md one-command setup in that clone.
4. Push with `runuser -u claude -- env -i bash -c '...'`, sourcing a small env
   file that sets `HOME`, `PATH`, the proxy variables, and the CA variables.

## Still open

- `workflow-local-run` needs the `gh act` extension. Neither user had it, and
  installing it needs the operator's approval. It fires only when a pushed
  change touches workflow files.
- `tests/validation/test_git_hook_policy_causal_restore.py::TestAdrReviewPolicyMergeScope::test_a_signed_history_is_still_read`
  needs the session's commit-signing service, whose config is readable only by
  root.
