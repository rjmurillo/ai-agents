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
4. Point `TMPDIR` at tmpfs (`/dev/shm/<user>-tmp`, mode 700). The base-derived
   count ratchets each materialize the base tree (about 1 GB) into a scratch
   directory. On the container disk `count-ratchets` hit its 84s cap; on tmpfs
   it finished in 67s and the push passed.
5. Install `gh act` for the user. `gh extension install` is refused by the
   session proxy, but GitHub release downloads work: fetch
   `act_Linux_x86_64.tar.gz` and `checksums.txt` from
   `github.com/nektos/act/releases/latest/download/`, verify with
   `sha256sum -c`, and install the `act` binary as
   `~/.local/share/gh/extensions/gh-act/gh-act`. `workflow-local-run` needs it
   whenever a push touches workflow files.
6. Push with `runuser -u claude -- env -i bash -c '...'`, sourcing a small env
   file that sets `HOME`, `PATH`, `TMPDIR`, the proxy variables, and the CA
   variables (`SSL_CERT_FILE`, `GIT_SSL_CAINFO`, `NODE_EXTRA_CA_CERTS`,
   `npm_config_cafile`; npm fails markdownlint with `SELF_SIGNED_CERT_IN_CHAIN`
   without the last two).

## Still open

- `tests/validation/test_git_hook_policy_causal_restore.py::TestAdrReviewPolicyMergeScope::test_a_signed_history_is_still_read`
  needs the session's commit-signing service, whose config is readable only by
  root. Commit as root (signing), then run checks and push as the non-root
  user.
