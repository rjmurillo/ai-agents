# Skill: Serializing concurrent pushes without stalling the fleet (95%)

## Statement

The push race in this repo is **same branch**, not same repo. Two agents
pushing the same ref collide and the loser reports `cannot lock ref ...
reference already exists`, usually after the work already landed. The obvious
guard is a single lock file:

```bash
flock /tmp/aiagents-push.lock git push origin "$BR"
```

That guard is correct and far too wide. This repo's pre-push hook runs a large
pytest subset and takes roughly 11 minutes per push. A global lock turns N
concurrent pushes into N serial hook runs even when every push targets a
different ref, and pushes to different refs never contended in the first place.

Measured on 2026-08-02 with five queued pushes to five distinct branches:

```
1183836  48:45  flock /tmp/aiagents-push.lock git push ... rjmurillo/eureka-ratchet-grep
1556659  40:35  flock /tmp/aiagents-push.lock git push ... chore/measurement-validity-rule
1710429  37:25  flock /tmp/aiagents-push.lock git push ... fix/script-entrypoints-and-pins
2201560  29:09  flock /tmp/aiagents-push.lock git push ... fix/test-locale-codec
3704323  05:36  flock /tmp/aiagents-push.lock git push ... fix/pre-pr-runs-ratchets
```

Four of the five were burning wall clock waiting on a lock that protected
nothing they could collide with.

## Recipe

Scan slots non-blocking; take the first free one. This gives the same
one-at-a-time guarantee as the old per-branch scheme without making different
branches contend on the same slot.

```bash
cd <your worktree>
BRANCH=$(git branch --show-current)
for s in 0 1 2 3; do
  SKIP_SCOPE_CHECK=1 flock -n --conflict-exit-code 99 "/tmp/aiagents-push-$s.lock" \
    git push --force-with-lease origin "HEAD:$BRANCH" \
    > ~/src/scratch/push-$BRANCH-s$s.log 2>&1
  rc=$?
  if [ "$rc" -ne 99 ]; then
    echo "SLOT=$s PUSH_RC=$rc"
    break
  fi
done
```

`--conflict-exit-code 99` is load-bearing. Without it, `flock -n` returns 1
for both "lock busy" and "command failed", making the two indistinguishable.
With 99, only a busy lock produces 99; every other code is the real git result.

Do NOT use a fixed hash (`SLOT=$(( ... % 4 ))`). A hash is a partition: it
maps a branch name to a fixed slot regardless of load. Measured 2026-08-03:
slot 2 had 9 holders and a 68-minute oldest waiter while slot 3 was idle.
Three branches all hashed to slot 2. The scanner always finds the idle slot.

## Evidence that it is safe

Verified by running one push under a per branch lock while three others held
the global lock. It completed normally and concurrently:

```
   ba4ad6a367..e7a0e00b77  chore/measurement-validity-rule -> chore/measurement-validity-rule
REAL_EXIT=0
elapsed=662s
```

No `cannot lock ref`, no rejected update, and 662 seconds is a single hook run
rather than a queue position. Git takes its ref lock per ref, and concurrent
object writes go to temp files and are renamed into place, so two pushes of
different branches from two worktrees of one clone do not contend.

## Why the wide lock looked right

The failure it was written for was real, and the first fix that stops a real
failure rarely gets re-examined. The lock was scoped to the tool (`git push`)
rather than to the resource the tool contends on (one ref). Scoping a guard to
the operation instead of the contended resource is the general shape, and it is
invisible until throughput matters, because correctness never regresses. It
only ever gets slower.

## One scheme, or none

`flock` excludes only processes that open the *same path*. Two lock schemes
running at once therefore produce two disjoint groups that cannot see each
other, and the guard silently stops guarding while still looking present in
every command line. A partially adopted lock is worse than no lock, because it
reads as protection.

Observed live on 2026-08-02, not reasoned. Two processes were pushing the same
branch at the same time under two lock paths that cannot see each other:

```
PID 761266  cwd ai-agents3-rebase-wt/pr4095
            flock /tmp/aiagents-push-2.lock
            git push --force-with-lease origin HEAD:fix/escaped-pipes-claude-skills

PID 3919969 cwd wt-4095
            flock ~/src/scratch/confc/push-lock-fix-escaped-pipes-claude-skills.lock
            git push origin fix/escaped-pipes-claude-skills
```

Both alive, both targeting the same remote ref, from two worktrees whose
contents were not identical. Whichever landed last decided the branch. Four
distinct schemes were in flight in that same `ps` listing: the 4 slot hash under
`/tmp`, the same 4 slot hash under `$HOME`, per branch locks under
`~/src/scratch/confc/`, and the canonical path below. A per branch lock in a
private directory is not safer than a global one, it is invisible.

One caution from the same listing. `flock X git push ...` spawns `git push` as a
child, so `ps` shows two entries per push with different elapsed times, because
`flock` starts when it begins waiting and the child starts when the lock is
acquired. That pair is not a double push. Check `ppid` before concluding one:
two of the three suspicious pairs there were parent and child.

So the recipe above is not a suggestion. Any agent or script that pushes in
this repo uses exactly this scanner with `/tmp/aiagents-push-$s.lock` and
nothing else. If you find another form in a prompt, a skill, or a memory,
correct it rather than adding a third. Historical records are the exception:
`.agents/retrospective/2026-07-31-test-infrastructure-cluster.md` records the
older `/tmp/aiagents-push.lock` as what was running at the time, and a
retrospective is evidence of a past state rather than instructions to follow.
Leave those alone; a grep for lock paths will keep surfacing them.

Two details that get "simplified" back into bugs:

- Every agent must use exactly the slot-scanner recipe above. `flock` excludes
  only processes that open the same path. A per-branch lock in a private
  directory or a different naming scheme is invisible to the fleet, not safer.
  `/tmp/aiagents-push-$s.lock` with `s` in `0..3` is the shared namespace.
- The `/tmp` wipe hazard still applies to the log, not to the lock. The lock
  is a kernel object held in the process's open file descriptor; if `/tmp` is
  wiped, the inode remains alive as long as any process holds it open. The log
  redirect fails immediately and silently. Put logs in `~/src/scratch/`, not
  `/tmp`. Locks stay in `/tmp` because every agent can name `/tmp`; the lock
  path must be universal, not durable.
- Capture the push status as `echo "PUSH_RC=$?"` immediately after the inner
  command, never through a pipeline. The scanner already does this via `rc=$?`.

## Related

- A backgrounded push outlives the shell that started it. Relaunching races the
  first, and the loser reports a conflict while the work HAS landed. Diagnose
  with `git rev-parse HEAD` against `git ls-remote origin "$BR"` before
  relaunching anything.
- A push log ending `Ready to create pull request!` does **not** mean the hook
  passed. It is `pre_pr.py` finishing one lefthook job, and it lands about 4%
  of the way through the run. Measured on three separate push logs from this
  repo, all three identical:

  ```
   995  RESULT: All validations passed
   997  Ready to create pull request!
  1000  ┃  group (2) ❯ python-tests ❯
  ...
  23286  ✔️ pre-pr-validation (60.07 seconds)
  ```

  `pre-pr-validation` takes about 60s. `python-tests` starts *after* the banner
  and takes about 866s, and the log runs to roughly 23,300 lines. So a log
  sitting at that banner has roughly 14 minutes still to go and is working
  normally.

  This is a trap with teeth, because the banner is the last human-readable
  sentence in the log and everything after it is pytest noise. Reading the tail
  gives you a confident and wrong "the hook is done, so the delay must be the
  network." That misdiagnosis cost a real session: it produced a push-stall
  hypothesis, a GitHub Status check, an events-API survey, and a killed process,
  none of which were relevant.

  Do not judge liveness from the log either. lefthook buffers each job's output
  and flushes it when the job ends, so the file sticks at roughly 1000 lines for
  the entire 14 minute `python-tests` run and then jumps to about 23,300 at
  once. A frozen log is the normal appearance of a healthy push, which is why
  the two signals confuse each other.

  The liveness signal that works is accumulated CPU on the pytest descendant:

  ```bash
  desc() { for c in $(pgrep -P "$1"); do echo "$c"; desc "$c"; done; }
  for p in $(desc <push-pid>); do
    ps -o pid=,time=,comm= -p "$p"
  done | grep -i pytest
  ```

  A healthy run shows the time column climbing (measured 00:04:07 at nine
  minutes elapsed). Zero and unmoving means hung. The direct child of the push
  always reads 00:00:00 because it sleeps while the hook runs, so read the
  descendant, not the child. Confirm the push itself with `git ls-remote`.
