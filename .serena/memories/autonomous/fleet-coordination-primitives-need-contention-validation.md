# Validate a fleet coordination primitive under contention before broadcasting it

## Pattern, observed twice in one session

I broadcast a push serialization mechanism to 30 plus concurrent agents. Twice.
Both designs were correct in isolation. Both were pathological under fleet load.
Both stalled the fleet worse than the problem they were introduced to solve.

**Incident 1.** A single `flock` around `git push`. Correct: it does serialize
pushes. Pathological: the pre-push hook runs a 7 to 15 minute validation suite
INSIDE the lock, so one global lock serialized the entire fleet's validation, not
just the ref transfer. Measured 28 waiting processes with a 57 minute oldest
waiter before I killed 12 of them.

**Incident 2.** The fix was four locks with the branch name hashed to a slot.
Correct: it is four times the concurrency. Pathological: a fixed hash partitions,
it does not schedule, so nothing balances load. Measured slot 2 holding nine
holders with three queued and a 68 minute oldest waiter while slot 3 sat
completely idle. My own push waited 51 minutes for a slot while a free one
existed.

## The common root cause

Both times I validated the mechanism's **correctness** (does it exclude?) and
skipped its **behavior under the actual arrival pattern** (what happens when 30
agents hit it with 10 minute critical sections?). Correctness is a property of one
caller. Convoying is a property of the population.

The tell in both cases was available in under a minute and I did not look for it:

```bash
for s in 0 1 2 3; do
  echo "slot $s: $(fuser /tmp/aiagents-push-$s.lock 2>/dev/null | wc -w) holders"
done
ps -eo pid,etimes,args | grep '[f]lock' | sort -k2 -rn | head
```

Any slot at zero while another has a queue is a load balancing failure, visible
immediately.

## Rule

Before broadcasting a coordination primitive to a fleet:

1. Name the critical section and measure its duration. If it is minutes rather
   than seconds, the mechanism is a scheduler problem, not a mutual exclusion
   problem, and mutual exclusion primitives will convoy.
2. Simulate or measure the arrival rate against that duration. N agents times a
   D minute section against K slots is a queueing model, and it either converges
   or it does not.
3. Instrument occupancy from the start. A mechanism with no way to observe
   whether it is balanced cannot be debugged when it is not.
4. Prefer take-any-free-resource over assign-by-identity whenever critical
   sections are long. A hash is fine for short uniform units; it is
   catastrophic when one collision costs more than the mechanism saves.

## Second-order cost

Broadcasting a correction to 30 agents is not free. Each correction message
competes for the agents' attention with their actual assignment, and the second
correction undermines the credibility of the first. Getting a fleet-wide
mechanism right before broadcast is worth several times the cost of validating
it, because the retraction is expensive in a way the original broadcast is not.

## Boundary

This is not an argument against acting fast on a measured problem. Both
interventions were correct responses to real, measured stalls. The defect was in
validating the fix against a single caller instead of against the population it
was about to be handed to. The remedy is one extra measurement, not more caution.
