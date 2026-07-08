# Root Cause Pattern: PreToolUse Bash Hook Wedge (fail-closed on host timeout)

**Pattern ID**: RootCause-Hooks-001
**Category**: Fail-Safe Failure (advisory hook becomes hard deny)
**Created**: 2026-07-08
**Source**: Live wedge during large agentic batch; Copilot CLI session denied every bash command.

## Symptom

Every Bash/shell command returns:

```
Denied by preToolUse hook from "repo settings" (hook errored)
```

- "repo settings" = Copilot CLI reads Claude Code's `.claude/settings.json` hooks and labels
  them "repo settings". These are Claude-style hooks (stdin JSON, exit 2 = block).
- "(hook errored)" = a hook exited non-zero WITHOUT a valid structured decision
  (crash / exception / spawn-fail / SIGKILL on host timeout). Copilot surfaces any non-zero
  repo-hook exit on a benign command as a hard deny.
- Onset correlates with large agentic batches (many concurrent sessions, degraded git state,
  grown `.serena/memories/` corpus). "If you're wedged, a customer is likely wedged too."

## Root Cause (structural class)

A per-tool-call PreToolUse hook that is designed to be advisory ("never blocks", fail-open on
exception) can still fail CLOSED and deny every command, because:

1. It does per-call work that can exceed the host hook timeout: a `git` subprocess (repo-identity
   via `skip_if_consumer_repo` -> `_remote_repo_name`) and/or an unbounded FS scan
   (`.serena/memories/**/*.md`, 800+ files).
2. When that work exceeds the host timeout, the host sends **SIGKILL**. A SIGKILL cannot be
   caught by the hook's internal `try/except` fail-open path, so the "advisory" contract is
   silently violated and the non-zero exit becomes a hard deny.
3. Concrete mismatch found: `_remote_repo_name` used `subprocess.run(..., timeout=5)`. The guard
   runs under multiple PreToolUse hosts; the tightest is topical-memory-injection at 2s
   (`.claude/settings.json`), and the correction-applier host is 3s. Internal timeout (5s) >
   tightest host timeout (2s) guarantees a SIGKILL before the internal timeout can return gracefully.

## Five Whys

- Q1: Why is bash denied? -> A repo-settings PreToolUse hook exits non-zero on a benign command.
- Q2: Why non-zero on benign command? -> The host SIGKILLs the hook at its timeout.
- Q3: Why does it hit the timeout? -> It runs a git subprocess (and/or scans 800+ memory files)
  whose worst-case wall-clock exceeds the host timeout.
- Q4: Why does the fail-open path not save it? -> A SIGKILL is uncatchable; `try/except` only
  covers in-process exceptions, not host-timeout kills.
- Q5: Why was the internal timeout larger than the host timeout? -> The subprocess timeout (5s)
  was set without reference to the tightest host hook timeout (2s) that invokes it.

## Invariant (the durable lesson)

> A per-tool-call hook's total wall-clock, including every subprocess it spawns and every FS
> scan it performs, MUST stay strictly under the tightest host hook timeout that invokes it.
> Otherwise a host SIGKILL turns a fail-open hook into a hard "hook errored" deny of every command.

Corollary: bounding a scan with a deadline anchored at *scan start* is insufficient when a
subprocess (git) runs *before* the scan under the same host budget. Anchor the deadline at the
hook's entry (`main()` start) and pass it through, so a slow subprocess shrinks the scan window
instead of pushing total wall-clock past the host timeout.

## Fixes applied (this session, committed in this PR)

- `scripts/hook_utilities/guards.py` (+ synced copies `.claude/lib/...`,
  `src/copilot-cli/lib/...`): `_remote_repo_name` git subprocess `timeout=5` -> `timeout=1`, so
  the per-tool-call git lookup stays under the 2s tightest host timeout (topical-memory-injection
  in `.claude/settings.json`). Failure still degrades to
  None -> identity "unknown" -> pyproject `[project].name` corroboration keeps project identity
  correct. No generator run needed (straight lib sync; all three copies edited identically).
- `.claude/hooks/PreToolUse/invoke_correction_applier.py` (+ generated Copilot mirror
  `src/copilot-cli/hooks/PreToolUse/invoke_correction_applier__Bash_f620ca.py`, regenerated via
  `build/scripts/generate_hooks.py`): bounded the `.serena/memories` scan
  (`_MAX_FILES_SCANNED`, `_MAX_TOTAL_BYTES`, wall-clock deadline) AND anchored a
  `_HOOK_WALL_BUDGET_SECONDS = 2.5` deadline at `main()` entry, passed into `scan_memories`, so
  git-time + scan-time together stay under the correction-applier host timeout (3s). The directory
  walk itself is now bounded during lazy `rglob` iteration (see `_collect_memory_files`): the prior
  `sorted(rglob(...))` materialized and ordered the entire tree before any cap applied, which on an
  800+ file corpus could blow the host timeout this hook exists to prevent. `scan_memories` also
  clamps a caller-supplied hook-wide deadline to its own `_SCAN_DEADLINE_SECONDS` budget.
- `tests/test_hook_plugin_guards.py::test_origin_lookup_timeout_under_host_budget`: regression
  guard. Reads `.claude/settings.json`, takes the minimum explicit PreToolUse hook timeout, and
  asserts the git lookup timeout is strictly less than it. Catches both a future git-timeout
  increase and a host-timeout decrease. Mirrors the #2811 `call_args.kwargs["timeout"]` pattern.

## What was NOT confirmed

The EXACT live crasher was not pinpointed by static analysis alone (bash/gh were wedged, so no
hook could be executed to capture the actual error). Two on-disk edits during the wedge did NOT
unblock the running session, which indicates Copilot snapshots repo hooks at session start:
**only a Copilot CLI restart reloads `.claude/settings.json` + hooks and clears the wedge.**

## Post-restart diagnostic (pinpoint in seconds once bash works)

Feed a benign payload to each configured Bash-matcher hook and check exit code + duration:

```
echo '{"tool_name":"Bash","tool_input":{"command":"echo diagnostic"}}' \
  | timeout 10 python3 .claude/hooks/PreToolUse/<hook>.py ; echo "exit=$?"
```

Any hook that exits non-zero (or is killed by `timeout`) on this benign input is the crasher.

## Detection Signals

- Every bash command denied with "(hook errored)" from "repo settings".
- Harness reports "Not a git repository" or `.git` is degraded/bloated.
- `.serena/memories/` has grown large (hundreds/thousands of files).
- Onset immediately after a large multi-session agentic batch.

## Related

- Timeout-hardening convention: `tests/test_timeout_hardening_2811.py`,
  `tests/test_security_gate_timeouts_2810.py` (issues #2810/#2811): subprocess calls must pass a
  timeout and degrade `TimeoutExpired` to a handled result). This wedge is the next layer:
  the subprocess timeout must also be *smaller than the host hook timeout*.
- Static hook contract validator: `scripts/validation/hook_contracts.py` validates settings.json
  timeout range (1-300) and exit-code docs, but does NOT yet cross-check internal subprocess
  timeouts against host timeouts. Candidate future gate.
- Consumer-repo identity guard rationale: issue #2610 (git-origin authoritative, not `.agents/`).
