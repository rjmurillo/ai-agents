# Tracking-branch push fails under this session's own fleet CPU/memory load, not a real regression

## Statement

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

## Recipe

Before retrying a failed tracking/bookkeeping push under known heavy fleet
load, check current contention rather than blindly re-running:

```bash
ps aux | grep -E "pre_pr.py|git push" | grep -v grep | wc -l
```

A count near 0 means it is a good moment to retry. A push launched into a
count of 5+ concurrent `pre_pr.py` runs is likely to fail the same way again.
This is advisory, not a guarantee: load can spike again mid-run (v46-v48 above
all started with a low count and still failed), so treat repeated failures
as expected fleet noise, not a regression to root-cause, and just retry with
the standard flock'd background-push-plus-monitor pattern:

```bash
mkdir -p "$HOME/src/scratch/locks"
LOGFILE=".../push_session_branch_vN.log"
nohup bash -c '
flock "$HOME/src/scratch/locks/push-lock-<slug>.lock" git push -u origin <branch> > "'"$LOGFILE"'" 2>&1
echo "PUSH_REAL_EXIT=$?" >> "'"$LOGFILE"'"
' > /dev/null 2>&1 &
disown
```

Then arm a one-shot `Monitor` polling for `PUSH_REAL_EXIT=` in the log rather
than sleeping or re-checking manually; grep the log for `PUSH_REAL_EXIT=`
specifically; a backgrounded shell's own reported exit code is the wrapper's,
not `git push`'s (see `git-lock-pushes-per-branch-not-globally.md`'s
`REAL_EXIT` note for the same trap in a different form). Do not treat a
`[FAIL] Generated Artifact Staleness` or a `pre-pr-validation` timeout as a
real defect in the branch's diff without first checking whether the fleet was
under load at push time.

## A second failure mode: OOM-kill, not CPU timeout

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

Same recipe applies: retry with the flock'd background-push-plus-monitor
pattern once `free -h` shows several GB available, and treat a repeat
`exit -9`/`killed on timeout` on `build_all.py --check` as this pattern,
not a code regression, unless the diff itself changed `build_all.py`.

## Why this isn't worth root-causing further

The underlying gate (`check_generated_staleness.py`'s `_GATE_BUDGET_SECONDS =
60.0` for `sync_plugin_lib.py --check` + `build_all.py --check`) is
deliberately tight on a quiet machine and was never designed to hold under
N concurrent worktree agents each spawning their own subprocess tree. Loosening
it would weaken the real signal it protects (generated-file staleness) for
the common case to accommodate an unusual one (this session's own heavy
self-imposed fan-out). Retry-with-a-load-check is the cheaper fix and costs
nothing when load happens to already be low.
