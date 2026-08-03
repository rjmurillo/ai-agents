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

Write scratch files and logs to `~/src/scratch/`, never `/tmp`. The lock uses
the slot-scanner recipe; the log path uses `~/src/scratch/` to survive `/tmp`
wipes.

```bash
S=~/src/scratch/locks; mkdir -p "$S"
SCRATCH=~/src/scratch; mkdir -p "$SCRATCH"
BRANCH=<branch>
for s in 0 1 2 3; do
  SKIP_SCOPE_CHECK=1 flock -n --conflict-exit-code 99 "$S/aiagents-push-$s.lock" \
    git push --force-with-lease origin "HEAD:$BRANCH" \
    > "$SCRATCH/push-$BRANCH-s$s.log" 2>&1
  rc=$?
  if [ "$rc" -ne 99 ]; then
    echo "SLOT=$s PUSH_RC=$rc"
    break
  fi
done
```

Both lock files and logs go in `~/src/scratch/` (locks under `~/src/scratch/locks/`).
`/tmp` is wiped periodically: a wiped log redirect fails silently, and even the
inode-survives-wipe argument for lock files breaks when the lock file is unlinked
while held. A new push recreates the path and `flock` opens a fresh inode, so two
processes can hold different inodes at the same path simultaneously. Keep both
locks and logs out of `/tmp`.

The log alone cannot tell you which of four states you are in. Read it together
with the process table and the `REAL_EXIT` sentinel.

| Log | `REAL_EXIT` | Process | State |
|---|---|---|---|
| missing | absent | none | launch failed, the redirect had nowhere to write |
| growing | absent | alive | still working, leave it alone |
| full, ends on a success line | absent | none | killed midway, relaunch is correct |
| any | present | none | finished, read the code |

The table answers whether the push finished, never what it carried. A clean
`REAL_EXIT=0` on a detached worktree pushes the wrong commit and looks identical
to success; see `git-empty-hook-run-means-an-empty-push` for the content check.

Measured on 2026-08-02: a 78 KB push log ended on `pre_pr.py` printing
`Ready to create pull request!`, which reads exactly like completion. There was
no `REAL_EXIT` line, no process, and `git ls-remote` still showed the old head.
The push had been killed under machine load with the whole test suite still to
run. The sentinel is the only completion signal in the log that means anything.

Detect the process by the branch name, never by the refspec. The command is
usually written `git push origin HEAD:<branch>`, so a grep for
`git push origin <branch>` matches nothing while the push is very much alive.
That miss reads as "the push died" and invites a relaunch, which queues behind
the first one on the flock and doubles the machine load.

```bash
# reliable: the branch alone, plus the worktree the push runs in
ps -eo pid,etimes,args | grep "$BR" | grep -v grep
for p in $(ps -eo pid --no-headers); do
  case "$(readlink /proc/$p/cwd 2>/dev/null)" in
    *"$(basename "$WT")"*) echo "$p $(tr '\0' ' ' < /proc/$p/cmdline)";;
  esac
done
```

Measured on 2026-08-02: `grep 'git push origin docs/memory'` returned nothing
against a push that had been running for 650 seconds as
`git push origin HEAD:docs/memory-red-main-blocks-push`.

## Three adjacent traps

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

Put the `cd` inside the process you launch. Writing
`cd "$WT" && nohup setsid ... &` backgrounds the entire `&&` list, so the `cd`
happens in the subshell and the parent shell never moves. Every command after
it in the same invocation runs in the original directory. With several
worktrees sharing one repository that is silent and dangerous: `git rev-parse
HEAD` answers for a different branch and the output looks completely normal.

```bash
# wrong: the cd is backgrounded along with everything else
cd "$WT" && nohup setsid bash -c "git push origin $BR > $S/p.log 2>&1" &

# right: the cd belongs to the launched shell, and follow-ups name the path
nohup setsid bash -c "cd '$WT' && git push origin $BR > $S/p.log 2>&1; \
  echo REAL_EXIT=\$? >> $S/p.log" >/dev/null 2>&1 &
git -C "$WT" rev-parse HEAD
```

Demonstrated 2026-08-02: `cd alpha && sleep 0.2 &` followed by `pwd` in the
same invocation printed `beta`, the starting directory.

## Generalization

A watcher that reports through the same channel it is watching cannot report
that channel's failure. Whenever the evidence of liveness and the mechanism of
liveness share a dependency, verify liveness by a second, independent route:
here, `ps` and `git ls-remote` rather than the log the process writes.
