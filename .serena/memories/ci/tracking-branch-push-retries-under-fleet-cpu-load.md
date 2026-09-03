# Tracking-branch push failures blamed on fleet CPU/memory load, root-caused and fixed by PR #5464

## Status: fixed at the source, keep this file for the diagnosis trail only

PR #5464, "fix(build): exclude ignored directories by prefix and stop at git
boundaries", merged 2026-09-02 and closed issue #5370. It stops
`build_all.py --check` at nested git boundaries, so the OOM-kill this file
diagnoses no longer has a source. The retry recipes below are history.

Current guidance: a repeat `exit -9` or `killed on timeout` on
`build_all.py --check` after #5464 is a NEW regression. Read the failing log
and open an issue. Do not retry it away as fleet noise, and do not cite this
memory as evidence that it is noise.

## Statement (as observed before #5464)

When a session runs many concurrent worktree agents (each running its own
`pre_pr.py`/pytest validation), a push on an unrelated branch can fail its
own pre-push `pre-pr-validation` lefthook job purely from CPU contention,
even though nothing about that branch's diff is broken. Retrying once load
drops usually succeeds with no code change.

## Evidence

One session pushing a session-bookkeeping tracking branch (`claude/ai-agents-issues-triage-vtndg7`)
while a 13-PR fix workflow ran dozens of parallel `wf_*` worktree agents hit
this five times in a row on 2026-08-27:

```
v45: [FAIL] build_all.py --check failed (exit -9)          -> PUSH_REAL_EXIT=1
v46: pre-pr-validation (227.77s)                            -> PUSH_REAL_EXIT=1
v47: pre-pr-validation: timeout (4m0s) (240.69s)            -> PUSH_REAL_EXIT=1
v48: pre-pr-validation (236.65s)                            -> PUSH_REAL_EXIT=1
v49: succeeded once `ps aux | grep pre_pr.py` read near zero
```

`exit -9` is SIGKILL (OOM-killed or hard-timeout-killed), not a validation
failure. `pre-pr-validation` normally finishes in the neighborhood of 60s
(see `git/git-lock-pushes-per-branch-not-globally.md`'s ~60s figure for the
same job on a quiet machine); here it repeatedly ran 4x over that under load
before the wrapping lefthook step timeout (240s) or the OS killed it outright.

## Historical: the retry recipe used before #5464

Superseded by PR #5464. Read this as a record of what was done in August 2026,
not as an instruction. A repeat `exit -9` or `killed on timeout` on
`build_all.py --check` today is a new regression to root-cause, not noise to
retry through.

The recipe was: before retrying a failed tracking/bookkeeping push under known
heavy fleet load, check current contention rather than blindly re-running.

```bash
ps aux | grep -E "pre_pr.py|git push" | grep -v grep | wc -l
```

A count near 0 was read as a good moment to retry. A push launched into a
count of 5+ concurrent `pre_pr.py` runs was expected to fail the same way
again. That reading was advisory and it was also wrong about the cause:
load spiked again mid-run (v46-v48 above all started with a low count and
still failed) because the real driver was the snapshot walk #5464 fixed, not
contention. The session then retried with the flock'd
background-push-plus-monitor pattern:

```bash
mkdir -p "$HOME/src/scratch/locks"
LOGFILE=".../push_session_branch_vN.log"
nohup bash -c '
flock "$HOME/src/scratch/locks/push-lock-<slug>.lock" git push -u origin <branch> > "'"$LOGFILE"'" 2>&1
echo "PUSH_REAL_EXIT=$?" >> "'"$LOGFILE"'"
' > /dev/null 2>&1 &
disown
```

The push-monitoring half of that recipe is still correct and is the only part
worth reusing: arm a one-shot `Monitor` polling for `PUSH_REAL_EXIT=` in the
log rather than sleeping or re-checking manually, and grep the log for
`PUSH_REAL_EXIT=` specifically, because a backgrounded shell's own reported
exit code is the wrapper's, not `git push`'s (see
`git-lock-pushes-per-branch-not-globally.md`'s `REAL_EXIT` note for the same
trap in a different form).

The diagnostic half is not. This section used to end by telling readers not to
treat a `[FAIL] Generated Artifact Staleness` or a `pre-pr-validation` timeout
as a real defect without first checking fleet load. After #5464 that is
backwards: read the failing log first. Fleet load explains a wall-clock
`pre-pr-validation` timeout under a genuinely busy machine and nothing else,
and it never explained the `exit -9`.

## Root cause found: not fleet load at all, see issue #5370

The OOM-kill mechanism below is NOT fleet contention. Root-caused 2026-08-27
(issue #5370): `build_all.py --check` OOM-kills itself standalone, with zero
other processes running, whenever `.claude/worktrees/` holds enough registered
git worktrees. Its REQ-003-010 snapshot guard (`_snapshot_owned_prefixes`)
walks `.claude/` with `rglob("*")` and reads every file's bytes into memory;
that walk has no embedded-repository boundary awareness, so it descends into
every nested worktree checkout under `.claude/worktrees/<name>/` and reads
each one's full working-tree content. Memory scales with worktree count, not
with concurrent process count. The fix was in `build_all.py`, not in retry
timing, and it landed: PR #5464 merged 2026-09-02 and closed this issue.
Retrying with a load/memory check was the workaround only until then. Pruning
stale worktrees under `.claude/worktrees/` (see issue #4193, the GC script that
exists but isn't wired up) remains useful for disk and registry hygiene, but is
no longer needed to keep this gate alive.

## Historical: a second failure mode, OOM-kill rather than CPU timeout

The same session hit three more consecutive failures (v74-v76, 2026-08-27) with
`ps aux | grep -E "pytest|pre_pr"` reading 0-7 (load looked clear) and `free -h`
showing 12-14Gi available immediately before each retry. Each still failed:

```
[FAIL] build_all.py --check failed (exit -9). Examined 2 of 2 checks.
[FAIL] build_all.py --check was killed on timeout; the tree was never scored.
```

`dmesg` showed the real cause was a memory-cgroup OOM kill, not CPU starvation:

```
oom-kill:constraint=CONSTRAINT_MEMCG, task=python3, pid=8633
Memory cgroup out of memory: Killed process 8633 (python3)
  total-vm:13605188kB anon-rss:13370104kB
```

One `build_all.py --check` invocation grew to ~13.4GB RSS on a 15GB-total
container and got killed by the memcg limit, not the 240s lefthook timeout.
`ps`-based load checks (count of `pytest`/`pre_pr` processes) do not see this:
a single heavy `build_all.py` run, or a handful of concurrent ones each holding
large working sets, can exhaust memory while the process *count* looks idle.
Check `free -h` (available column) in addition to the process count before
retrying; a push launched when available memory is in the low single digits
of GB is as likely to fail as one launched into high CPU contention, even
though `ps` reports near-zero load.

That was the recipe at the time: retry with the flock'd
background-push-plus-monitor pattern once `free -h` shows several GB available.
It no longer applies. After #5464 a repeat `exit -9` or `killed on timeout` on
`build_all.py --check` is a new regression, whatever the diff touched. Open the
log and root-cause it instead of retrying.

## Superseded: why this looked like it wasn't worth root-causing

This section was wrong, and #5464 is the proof. It is kept because the reasoning
is a useful example of how a real defect gets argued into being ambient noise.

The argument ran: the underlying gate (`check_generated_staleness.py`'s
`_GATE_BUDGET_SECONDS = 60.0` for `sync_plugin_lib.py --check` +
`build_all.py --check`) is deliberately tight on a quiet machine and was never
designed to hold under N concurrent worktree agents each spawning their own
subprocess tree, so loosening it would weaken the generated-file-staleness
signal for the common case, and retry-with-a-load-check is the cheaper fix.

What that missed: the memory usage was not the fan-out's fault at all. One
`build_all.py --check` reached 13.4GB standalone because its snapshot guard read
every nested worktree's files. Root-causing it cost one issue and one PR, and
the retry loop it replaced had already burned nine pushes. When a gate fails
repeatedly and the load explanation needs a caveat each time, read the log.
