# Rollout validity

Read this before the baseline step and again before you trust a result. A bad
rollout poisons the gate, because the gate only compares the booleans you give
it.

## Preflight each task

Before a rollout, check the prompt, the verifier, the required inputs, the
initial fixtures, and the permitted action scope. Then take these branches:

- Required input is missing, or the verifier demands work the task never
  authorized: mark the task `"status": "invalid"` and replace it before scoring.
- Authorization reaches live external state: mark it `invalid` and replace it
  with a sandboxed task. Do not run it.
- The agent safely refuses an action the task never authorized: that is not a
  skill failure. Fix the task, not the skill.
- The task authorizes sandbox writes: do not add a response-only or no-write
  restriction. Do not grant access the task does not authorize. Match the
  authorization in the task exactly.
- The wrong skill, the wrong manifest, or a scope change reached the rollout:
  the rollout is invalid, not a pass or a fail. Keep it as invalid. Rerun it
  under the original scope only when its inputs and fixtures are unchanged.

For a task that writes to scratch space: inspect the root before setup, seed
only the declared fixture, confine writes to the named sandbox, and inspect the
actual outputs and changed paths yourself.

## Grade from the artifact

Grade the complete persisted output against every clause of the frozen
verifier. A `Pass only if` list is conjunctive. A required step or artifact
that is not stated or shown is missing, not implied. A runner's self-check or
a delegated summary is not proof: read the persisted response and artifacts,
and verify their hashes and scope. An answer that is clipped, missing, or
contradicts its recorded label is `"UNVERIFIED"` until you recover the full
artifact or rerun against unchanged inputs.

## Audit changes the numbers

Invalid and exposed tasks do not count toward a held-out score. If an audit
changes any result, update the results files, then rerun `score`, `pair-gate`
(or `efficiency-gate`), and any null control before you report. A verdict
computed before the audit is stale.
