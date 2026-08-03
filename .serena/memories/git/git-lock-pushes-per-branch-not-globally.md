# Skill: Serializing concurrent pushes without stalling the fleet (95%)

## Statement

The push race in this repo is **same branch**, not same repo. Two agents
pushing the same ref collide and the loser reports `cannot lock ref ...
reference already exists`, usually after the work already landed. The obvious
guard is a single lock file:

```bash
# push-lock-historical: the superseded global scheme, kept as evidence
flock /tmp/aiagents-push.lock git push origin "$BR"
```

That guard is correct and far too wide. This repo's pre-push hook runs a large
pytest subset and takes roughly 11 minutes per push. A global lock turns N
concurrent pushes into N serial hook runs even when every push targets a
different ref, and pushes to different refs never contended in the first place.

Measured on 2026-08-02 with five queued pushes to five distinct branches:

```
push-lock-historical: ps output from the superseded global scheme
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
mkdir -p "$HOME/src/scratch/locks"
flock "$HOME/src/scratch/locks/push-lock-$SLUG.lock" git push origin "$BR"
```

The path is canonical and `.claude/rules/push-lock.md` owns it. It moved off
`/tmp` because a wipe there splits one filename across two inodes and the
holders stop excluding each other; three schemes were live at once on
2026-08-02 (issue #4366). Do not spell it any other way: `flock` excludes only
processes that open the same path, so a second name is not a second lock.

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

## Related

- A backgrounded push outlives the shell that started it. Relaunching races the
  first, and the loser reports a conflict while the work HAS landed. Diagnose
  with `git rev-parse HEAD` against `git ls-remote origin "$BR"` before
  relaunching anything.
- A push log ending `Ready to create pull request!` means the hook passed, not
  the push. Confirm against the remote ref.
