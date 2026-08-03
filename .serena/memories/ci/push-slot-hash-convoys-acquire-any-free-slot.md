# Push semaphore: a hashed slot convoys, acquire any free slot instead

## Symptom

Your push sits for tens of minutes with a zero-byte log file. `git push` has not
started at all; the process is blocked in `flock`. Meanwhile other pushes on the
same box complete normally, and at least one lock slot is completely idle.

## The recipe that causes it

This shape circulated through the fleet and is wrong:

```bash
SLOT=$(( $(printf '%s' "$BRANCH" | cksum | cut -d' ' -f1) % 4 ))
flock /tmp/aiagents-push-$SLOT.lock git push --force-with-lease origin HEAD:"$BRANCH"
```

A fixed hash maps a branch name to a slot **regardless of whether that slot is
occupied**. It is a partition, not a scheduler. Nothing balances load.

## Measured census, 2026-08-02

| slot | flock holders | queued pushes | oldest waiter |
| --- | --- | --- | --- |
| 0 | 8 | 1 | 10m 36s |
| 1 | 8 | 1 | 10m 36s |
| 2 | 9 | 3 | 1h 8m |
| 3 | 0 | 0 | idle |

Slot 2 serialized three pushes while slot 3 sat idle. Each queued push holds its
slot for the FULL pre-push suite, 7 to 15 minutes, not for the ref transfer. So
a three deep queue is a 21 to 45 minute wait for the last entrant with a free
slot going unused the whole time. One of the three was mine at 51 minutes with a
zero-byte log.

This is a scheduling defect, not a throughput one.

## Fix

Acquire ANY free slot. Four slots is plenty; the slot count was never the
problem.

```bash
cd <worktree>; BRANCH=$(git branch --show-current)
for s in 0 1 2 3; do
  SKIP_SCOPE_CHECK=1 flock -n --conflict-exit-code 99 "/tmp/aiagents-push-$s.lock" \
    git push --force-with-lease origin "HEAD:$BRANCH" > ~/src/scratch/<name>.log 2>&1
  rc=$?; if [ "$rc" -ne 99 ]; then echo "SLOT=$s PUSH_RC=$rc"; break; fi
done
# all four busy: block rather than spin
```

Reusable script lives at `~/src/scratch/push_any_slot.sh`.

## The load-bearing flag

`--conflict-exit-code 99` is what makes this work at all. A bare `flock -n`
returns exit 1 both when the lock is busy AND when the command it ran failed, so
the loop cannot tell "try the next slot" from "the push failed, stop". With
`--conflict-exit-code 99`, exit 99 means only ever "lock busy", and every other
code is the real result of `git push`.

Verified: probe reported slot0 BUSY, slot1 BUSY, slot2 BUSY, slot3 FREE, exactly
matching an independent `fuser` census.

## Do not fix by raising the slot count

Raising 4 to 8 reduces collision probability and leaves the mechanism broken. A
fixed hash can always stack N branches onto one slot. The primitive is wrong,
not its parameter.

## Related: the lock excludes about two thirds of traffic

At the same census, three pushes were running with no lock in the command line
at all (bare `git push -u origin <branch>` and `nohup git push`). Six locked, three
unlocked. Compliant callers pay the queueing cost and get partial isolation.
Tracked in issue #4366. Deciding on one scheme matters more than tuning this one.

## Boundary

This is about the push semaphore specifically. It does not generalize to a claim
that hashed partitioning is always wrong: a hash is correct when work units are
short and uniform. It fails here because each unit holds its slot for 7 to 15
minutes, so a single unlucky collision costs more than the entire mechanism
saves.
