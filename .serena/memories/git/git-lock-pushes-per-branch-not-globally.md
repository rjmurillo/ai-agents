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

Key the lock on the branch, so it still blocks the collision that actually
happens and blocks nothing else.

```bash
BR=$(git rev-parse --abbrev-ref HEAD)
SLUG=$(printf '%s' "$BR" | tr '/' '-')
flock "/tmp/push-lock-$SLUG.lock" git push origin "$BR"
```

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

So the path above is not a suggestion. Any agent or script that pushes in this
repo uses exactly `/tmp/push-lock-<branch-with-slashes-replaced-by-dashes>.lock`
and nothing else. If you find another form in a prompt, a skill, or a memory,
correct it rather than adding a third.

Two details that get "simplified" back into bugs:

- The lock file stays in `/tmp`. It is a live kernel object and every agent must
  name it identically, so it cannot move to a per-user directory. The push *log*
  is the opposite case and belongs in `~/src/scratch`; `/tmp` was wiped
  mid-session on 2026-08-02 and a detached process whose redirect target had
  vanished reported nothing at all.
- Capture the push status as `echo "REAL_EXIT=$?"` immediately after the `git
  push`, never through a pipeline. `git push | tail -3; echo $?` reports
  `tail`'s status, which is always 0.

## Related

- A backgrounded push outlives the shell that started it. Relaunching races the
  first, and the loser reports a conflict while the work HAS landed. Diagnose
  with `git rev-parse HEAD` against `git ls-remote origin "$BR"` before
  relaunching anything.
- A push log ending `Ready to create pull request!` means the hook passed, not
  the push. Confirm against the remote ref.
