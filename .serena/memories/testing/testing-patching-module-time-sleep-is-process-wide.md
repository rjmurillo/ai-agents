# Patching `mod.time.sleep` patches every thread in the process

## Where the behavior lives

Testing rule 18 in `templates/rules/testing.md` owns the practice.
This memory keeps the incident record.

## The observation

"Patch where it is used" suggests `patch("get_pr_checks.time.sleep")` is local.
It is not. `get_pr_checks.time` is the shared `time` module object.
The patch sets `time.sleep` for every caller in the process.
That includes threads left over from earlier tests on the same xdist worker.

## Incident

PR #6935 changed only two memory files on 2026-10-25.
Run 40239896828, pytest (split-1), still failed:
`TestQueuedMissingMain::test_wait_stale_head_fails_at_once`.
The message was `Expected 'sleep' to not have been called. Calls: [call(0.05)]`.
The script under test only sleeps 10 seconds, so 0.05 came from elsewhere.
The caller was `_trickled_headers` in `tests/skills/api-doc-authoring/test_deadlines.py`.
It runs on a per-connection thread that `_serve_raw` did not join.
It sends 225 bytes at 0.05 seconds each, about 11 seconds.
Three local reruns passed, because the stray call must land inside a short test.
A plugin listing `threading.enumerate()` after each test found the leftover workers.

## Source

- Fix: PR #6937, branch `fix/test-deadlines-server-thread-leak`.
