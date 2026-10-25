# Patching `mod.time.sleep` patches every thread in the process

## The trap

"Patch where it is used" suggests `patch("get_pr_checks.time.sleep")` is local.
It is not. `get_pr_checks.time` is the shared `time` module object.
The patch sets `time.sleep` for every caller in the process.
That includes threads left over from earlier tests on the same xdist worker.

## What it looks like when it bites

PR #6935 changed only two memory files on 2026-10-25.
Run 40239896828, pytest (split-1), still failed:
`TestQueuedMissingMain::test_wait_stale_head_fails_at_once`.
The message was `Expected 'sleep' to not have been called. Calls: [call(0.05)]`.
The script under test only sleeps 10 seconds, so 0.05 came from elsewhere.
The caller was a trickle worker in `tests/skills/api-doc-authoring/test_deadlines.py`.
It outlived its test and slept 0.05 seconds per byte for about 10 seconds.
Three local reruns passed, because the stray call must land inside a short test.

## Practice

- A test server or worker thread must be joined before its test ends.
- Shut the sockets first, so a blocked `recv` or the next send returns.
- Prefer `stop.wait(pause)` over `time.sleep(pause)` inside test servers.
- To find a leaker, list `threading.enumerate()` after each test with a small plugin.
- A sleep-count assertion that fails with an odd argument points at another thread.

## Source

- Fix: PR #6937, branch `fix/test-deadlines-server-thread-leak`.
