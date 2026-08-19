---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-19-session-99922-b72ee9e6c-quiet-aptdpkg-noise-bootstrap-vmsh-session-startsession-end.json
qaCommit: 14de240eb063d59bc46a37423f842586544a1e5e
---
# QA Report: Quiet apt/dpkg Output in bootstrap-vm.sh (Issue #5169)

**SHA**: 14de240eb063d59bc46a37423f842586544a1e5e
**Date**: 2026-08-19
**Scope**: `scripts/bootstrap-vm.sh` (`quiet_run()`/`quiet_apt_get()` helpers,
covering all five bare `sudo apt-get`/`dpkg -i` call sites) and
`tests/test_bootstrap.py` (new committed regression coverage)

## Verdict

PASS. Rebinds evidence to `14de240eb`, which adds three PR-review-driven
fixes on top of the commit the original report bound to (`a5c27d9995`): the
`dpkg -i` call site now routed through the quiet wrapper, a real EXIT-trap
exit-code regression found and fixed during test-writing, and committed
subprocess regression tests replacing the ad hoc shim runs the first report
relied on.

## Evidence

| Check | Result |
|-------|--------|
| `bash -n scripts/bootstrap-vm.sh` | syntax OK |
| `uv run pytest tests/test_bootstrap.py -q` | 18 passed |
| `uv run ruff check tests/test_bootstrap.py` | all checks passed |
| `uv run mypy tests/test_bootstrap.py` | no issues |
| `tests/test_bootstrap.py::TestQuietAptGet::test_quiet_on_success` | extracts the real `quiet_run`/`quiet_apt_get` bodies from the script and runs them against fake `sudo`/`apt-get`; stdout/stderr silent aside from the caller's own marker |
| `tests/test_bootstrap.py::TestQuietAptGet::test_warnings_surface_even_on_zero_exit` | `W:` lines reach stderr despite the fake `apt-get` exiting 0 |
| `tests/test_bootstrap.py::TestQuietAptGet::test_failure_dumps_log_and_aborts` | logged output dumped to stderr, process exits non-zero, marker after the failing call never printed |
| `tests/test_bootstrap.py::TestQuietAptGet::test_apt_log_removed_on_exit` | `$APT_LOG` path no longer exists after the subprocess exits, confirming the EXIT trap fires |
| `tests/test_bootstrap.py::test_vm_bootstrap_has_no_bare_apt_get_or_unguarded_dpkg_i` | static check: every `apt-get`/`dpkg -i` occurrence in the script is routed through a `quiet_*` wrapper |
| Manual shim run reproducing Copilot's `dpkg -i` finding | before the fix, a fake `dpkg` printed unpack noise to stdout on the PowerShell path; after routing it through `quiet_run`, output is silent on success |
| Manual shim run reproducing the trap regression | `[[ -n "$TMP_DIR" ]] && rm -rf ...` as the EXIT trap returned exit 1 from an otherwise-successful run (TMP_DIR unset is the common case); confirmed the `if`-block fix returns 0 in the same scenario |

Extraction-based testing (regex-pulling the real function bodies out of the
script, per `.claude/rules/canonical-source-mirror.md`'s guidance against
self-referential test mirrors) is what surfaced the trap bug: the earlier ad
hoc shim runs in the first QA pass happened to always set `TMP_DIR`, or check
success without asserting the process's own exit code, and missed it.

## Notes

`ruff`/`mypy` now apply to `tests/test_bootstrap.py` (new `.py` content in this
round); `scripts/bootstrap-vm.sh` itself has no Python tooling.
