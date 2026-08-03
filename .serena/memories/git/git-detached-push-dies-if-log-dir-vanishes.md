# Skill: A detached process dies silently when its log directory disappears (90%)

## Statement

A long push in this repo takes roughly 660 seconds, so the working pattern is
to detach it and poll a log:

```bash
nohup setsid bash -c "flock /tmp/push-lock-$SLUG.lock git push origin $BR \
  > /tmp/r16/push.log 2>&1; echo REAL_EXIT=\$? >> /tmp/r16/push.log" >/dev/null 2>&1 &
```

If the log directory is under `/tmp` and `/tmp` is cleaned while the session is
running, the redirect has nowhere to write and **the command never starts**.
There is no error anywhere, because the only channel that would have carried
one was the redirect that failed. Polling the log looks identical to a push
that is still working: no `REAL_EXIT` line, no output.

Measured on 2026-08-02: a P0 push was believed in flight for about ten minutes.
`/tmp/r16` had been removed mid-session. `ls -la /tmp/r16/` returned
`No such file or directory` and `ps` showed no `git push` process at all.

## Recipe

Write scratch files and logs to `~/src/scratch/`, never `/tmp`. Keep the lock
file itself at `/tmp/push-lock-<slug>.lock`: a lock is a live kernel object, not
an artifact, and every agent must agree on one path for mutual exclusion to
work. Only the log moves.

```bash
S=~/src/scratch; mkdir -p "$S"
BR=<branch>; SLUG=$(printf '%s' "$BR" | tr '/' '-')
nohup setsid bash -c "flock /tmp/push-lock-$SLUG.lock git push origin $BR \
  > $S/push-$SLUG.log 2>&1; echo REAL_EXIT=\$? >> $S/push-$SLUG.log" >/dev/null 2>&1 &
```

Then verify the process actually exists before trusting the wait:

```bash
sleep 5
test -f "$S/push-$SLUG.log" || echo "log missing, the redirect failed"
ps -eo pid,etime,args | grep "git push" | grep -v grep
```

An absent log file five seconds in means the launch failed, not that the push
is quiet.

## Two adjacent traps

Use `nohup setsid`. An async process merely backgrounded from the agent session
is killed when that session shuts down, for example at context compaction. Two
pushes were lost that way before the detached form was adopted.

Never confirm a push from its log alone. Compare the refs:

```bash
git ls-remote origin "$BR" | awk '{print $1}'
git rev-parse HEAD
```

An empty `git ls-remote` result for a branch that should exist is worth a second
look rather than a conclusion: after a squash merge GitHub deletes the source
branch, so "no remote ref" can mean "already merged" rather than "never pushed".
Check `gh pr view <n> --json state,headRefOid` before concluding anything.

## Generalization

A watcher that reports through the same channel it is watching cannot report
that channel's failure. Whenever the evidence of liveness and the mechanism of
liveness share a dependency, verify liveness by a second, independent route:
here, `ps` and `git ls-remote` rather than the log the process writes.
