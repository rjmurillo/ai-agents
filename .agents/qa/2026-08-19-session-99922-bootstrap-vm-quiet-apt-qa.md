---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-19-session-99922-b72ee9e6c-quiet-aptdpkg-noise-bootstrap-vmsh-session-startsession-end.json
qaCommit: a5c27d9995248d24e3479e9995fc0dbc9a1cc09d
---
# QA Report: Quiet apt/dpkg Output in bootstrap-vm.sh (Issue #5169)

**SHA**: a5c27d9995248d24e3479e9995fc0dbc9a1cc09d
**Date**: 2026-08-19
**Scope**: `scripts/bootstrap-vm.sh` (`quiet_apt_get()` helper, replacing four
bare `sudo apt-get` call sites)

## Verdict

PASS.

## Evidence

| Check | Result |
|-------|--------|
| `bash -n scripts/bootstrap-vm.sh` | syntax OK |
| `uv run pytest tests/test_bootstrap.py -q` | 13 passed |
| Functional shim test: success path (no drift) | stdout/stderr silent aside from the caller's own marker line; confirms dpkg unpack noise is suppressed |
| Functional shim test: success path with `apt-get update` emitting `W: GPG error ... NO_PUBKEY` / `W: Failed to fetch` while still exiting 0 | both warning lines reach stderr despite the zero exit; confirms the security-review fix (surfacing `^(W|E): ` lines) works |
| Functional shim test: real failure (`apt-get install` exits 100) | logged output is dumped to stderr and the wrapping script aborts (`set -e`), confirming the fail-loud contract is preserved |
| `Task(subagent_type="security", ...)` review of the first commit (6e3e7ef97) | found one Medium (apt warnings silenced on the success path); fixed in the follow-up commit (a5c27d999) and re-verified by the functional shim test above |

Shim tests were run standalone (fake `sudo`/`apt-get` on `PATH`, extracting the
`quiet_apt_get` function body via `awk`) rather than through a real `apt-get`,
since this sandbox has no safe way to mutate system package state. The shim
covers the three behaviors the change claims: quiet on success, loud on
failure, and warnings surfaced even on a zero exit.

## Notes

No `.py` files changed, so `ruff`/`mypy` do not apply to this diff.
`scripts/validation/pre_pr.py`'s "Session End Validation" gate is what
required this report; the `investigation-only` QA-skip path was rejected
because `scripts/bootstrap-vm.sh` is a real code change, not investigation-only
work.
