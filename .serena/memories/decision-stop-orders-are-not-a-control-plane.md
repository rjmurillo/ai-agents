# Decision: a message stop order is not a control plane for shared-machine contention

## Question

When many autonomous agents contend for one machine's CPU and one account's GitHub
API quota, is broadcasting a stop order to those agents an effective way to
recover throughput?

## Conventional answer

Yes. The agents are instruction-following. Tell them to stop, they stop. If they
did not stop, the order was not specific enough, so write a more specific order.
This is the reasoning I applied three times in a row, each time blaming my own
wording for the failure.

## First-principles position

No. A broadcast message is advisory, asynchronous, and scoped. It fails for three
structural reasons that no amount of rewording fixes.

1. **Scope.** `write_agent` reaches only the children of the session that spawned
   them. Any other agent process on the same machine is unreachable.
2. **Latency.** The message lands between tool calls. An agent already inside a
   25 minute `git push` cannot read it until that push returns, and the pre-push
   hook is exactly the resource being contended.
3. **Competing plan.** The agent has its own committed plan. A stop order is one
   input against a multi-step objective it is already executing.

The reliable lever is the resource, not the agent. Scheduling priority
(`renice`) and a real semaphore work across sessions, need no cooperation, and
apply the instant they are set.

## Evidence

Measured on this machine, 48 cores, 2026-08-03:

- Two independent `copilot --yolo --resume` processes were running: PID 3858342
  (started 06:21 Aug 3) and PID 27962 (started 09:57 Aug 2, roughly 32 hours
  earlier). Only the first was mine. `ps -o pid,ppid,lstart,args -p <pid>`
  showed both, and an ancestry walk attributed three of the concurrent
  `git push --force-with-lease` trees to PID 27962.
- After a stop order that explicitly enumerated retries, other branches, and
  nested `gh` calls, two new pushes from my own children started within four
  minutes of delivery (`fix/windows-ci-skill-size` at 249s elapsed,
  `fix/gate-enforcement-clean` at 242s).
- I had previously attributed a post-stop-order push to my own fleet. That
  attribution was wrong. The push belonged to the other session, which never
  received any order.
- Killing four of eight contending push trees dropped concurrent pytest from
  65 to 61 and load went **up**, because freed CPU let queued agents start new
  pushes. Five minutes later there were twelve hooks, one 47 seconds old.
- `renice -n 19` applied to 137 competing hook and test processes, protecting
  only the target worktree, let the protected suite finish in 1484s against a
  hard 1740s budget. Non-destructive, reversible, effective across both
  sessions.

## Decision

For shared-resource contention, act on the resource first and the agents second.

1. Measure before attributing. `ps -o pid,ppid,lstart,args` and an ancestry walk
   to each session root. Do not assume every competing process is yours.
2. Apply `renice -n 19` to competing processes, excluding the protected
   worktree. This is the only lever that crosses session boundaries without
   destroying work.
3. Send the stop order too, but treat compliance as best-effort and verify by
   measurement, never by the agents' replies.
4. Never kill to relieve congestion. Freed capacity is immediately consumed by
   queued starts, so kills convert other agents' completed work into nothing and
   leave the load unchanged.

## Transferable rule

An instruction is not a mechanism. When the failure mode is resource contention,
the fix lives in the scheduler or a semaphore, not in the prompt. Verify a stop
order by measuring the resource, never by reading the acknowledgements.
