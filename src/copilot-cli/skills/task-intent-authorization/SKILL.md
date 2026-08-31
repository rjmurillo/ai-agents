---
name: task-intent-authorization
version: 1.0.0
description: Distinguish assessment and diagnosis from mutation authorization before changing repository or external state. Diagnose problem reports before mutating. Mutation requires an explicit request or an already-authorized workflow. Once authorized and enough information exists, act without asking again.
license: MIT
user-invocable: true
---

# Task Intent Authorization

Separate understanding a problem from authorization to change state. This is the
canonical owner of entry into mutation. It does not redefine user sovereignty
(`builder-ethos`) or terminal completion (#5404); it composes with them.

## Triggers

- `should I fix this or just report it`
- `does this request authorize a change`
- `am I allowed to mutate here`
- `is this a diagnosis or a fix request`
- `classify request intent`

## Governing invariant

> Diagnose problem reports before mutating. Mutation requires explicit user
> authorization or an already-authorized workflow. Once mutation is authorized
> and enough information exists, act without asking again.

## Three semantic modes

| Mode | Meaning | Mutation |
|------|---------|----------|
| ASSESS | understand, explain, compare, evaluate | none implied |
| DIAGNOSE | inspect evidence, reproduce, identify cause | none implied unless the request also authorizes it |
| MUTATE | fix, update, apply, create, delete, send, merge, change state | requires explicit request or workflow authority |

## Authorization sources

Mutation may be authorized by:

- a direct imperative: `fix`, `update`, `apply`, `create`, `file`, `send`, `merge`, `change`, `delete`, or equivalent wording;
- an explicit lifecycle or remediation workflow whose contract includes mutation;
- a prior still-active instruction in the same task that authorized the scope;
- a repository-mandated automatic action whose authority policy already establishes.

Do not infer mutation authority merely because the defect is obvious, the fix is
small, a tool can perform it, the user asked `why` or `review` or `evaluate`, or
an adjacent issue surfaced during another task.

## Inverse guard: do not ask twice

Once the current request authorizes the action and enough information exists, act.
Do not ask a redundant permission question. Needing more information is a reason
to diagnose or gather, not a reason to re-request permission you already hold.

## Scope discipline

Authorization is bounded by the request. `Fix the failing test` authorizes the
smallest change that makes the test and its intended behavior correct. It does
not authorize unrelated cleanup, broad refactoring, dependency upgrades, or
documentation expansion. When diagnosis reveals a materially different or broader
action than the user authorized, surface that decision instead of silently
widening scope, unless an active workflow contract already covers it.

## Composition and ownership

- Entry into mutation: this skill.
- User sovereignty and bounded completeness: `builder-ethos` (reused, not duplicated).
- Terminal state and post-completion continuation: #5404.
- Truthful progress and completion reporting: #5405.
- Failure recovery and no-fabrication: #5392.

Deferred, mechanisms do not exist yet: #5396 capability-DAG wiring and #5391
placement-contract conformance. When those land, register ownership and
dependency metadata through them instead of restating policy here.

## Process

1. Classify intent. Read the leading verb, the conditional-fix pattern, and any active workflow signal to place the request in ASSESS, DIAGNOSE, or MUTATE.
2. Decide authorization. A question or problem report authorizes nothing. An explicit imperative or an already-authorized workflow authorizes the bounded change named in the request.
3. Apply the inverse guard. When authorized with enough information, act without a redundant permission question. When a proposed action exceeds the authorized scope, surface a new decision instead of widening it.

## Scripts

`scripts/classify_intent.py` makes the invariant runnable and deterministic.

```bash
python3 .claude/skills/task-intent-authorization/scripts/classify_intent.py "Why is this test failing?"
python3 .claude/skills/task-intent-authorization/scripts/classify_intent.py "Fix this failing test"
python3 .claude/skills/task-intent-authorization/scripts/classify_intent.py --workflow-authorized "apply the remediation"
```

Output is a JSON object with these keys:

| Key | Meaning |
|-----|---------|
| `intent` | `ASSESS`, `DIAGNOSE`, or `MUTATE` |
| `mutation_authorized` | whether the request authorizes a state change |
| `authorization_source` | `none`, `explicit_request`, `workflow`, or `conditional_fix` |
| `diagnosis_gated` | mutation allowed only after a confirmed cause |
| `authorized_targets` | explicit targets that bound the authorized scope |
| `reason` | short justification |

| Exit code | Meaning |
|-----------|---------|
| 0 | Classification produced |
| 2 | No request text provided |

Callable helpers for composition:

- `classify(request, workflow_authorizes_mutation=...)` returns the decision.
- `requires_permission_question(decision, have_enough_info)` returns False when authorized with enough info (act, do not ask again).
- `action_requires_new_decision(decision, proposed_targets)` returns True when a proposed action exceeds the authorized scope.

## Required scenarios

| Scenario | Expected behavior |
|----------|-------------------|
| `Why is this test failing?` | diagnose; no repository mutation |
| `Review this code for defects` | report findings; no fix unless a review workflow authorizes repair |
| `Fix this failing test` | diagnose then implement and verify; no redundant permission question |
| `Update issue #123 with this context` | read issue, update body; authorized mutation |
| `Evaluate whether we should change X` | evaluate; do not change X |
| `Investigate and fix if confirmed` | diagnosis gates mutation; a confirmed defect may be fixed without another permission round |
| authorizes file A fix, diagnosis suggests unrelated file B cleanup | do the required fix only; unrelated cleanup not implied |
| authorized workflow finds a materially broader or destructive action | stop for the decision unless the workflow contract already covers it |

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Treating an obvious defect as fix authority | A question is not a command | Diagnose, report, wait for an imperative |
| Asking permission after an explicit fix request | Redundant confirmation stalls authorized work | Act once authorized with enough information |
| Widening scope to unrelated cleanup | Authority is bounded by the request | Do the named change only; surface extras |
| Inferring authority from tool availability | Capability is not permission | Require an explicit request or workflow |

## Extension Points

- #5396 capability DAG: register ownership and dependency metadata when the mechanism lands, instead of restating policy here.
- #5391 placement contract: bind this owner to the placement semantics once that mechanism exists.
- New authorization sources: extend the mutation verb set or the workflow signal without weakening the assessment gate.

## Verification

- [ ] Question or problem report alone never sets `mutation_authorized` true.
- [ ] Explicit imperative sets `mutation_authorized` true, bounded by `authorized_targets`.
- [ ] Authorized workflow does not trigger a redundant permission question.
- [ ] Scope expansion beyond `authorized_targets` requires a new decision.

## Timelessness: 9/10

Separating comprehension from authority to change state is a durable
engineering discipline. It predates and outlives any single tool or workflow.
