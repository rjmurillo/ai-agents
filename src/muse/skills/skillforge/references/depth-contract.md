# Depth Contract

SkillForge sizes its work to the accepted outcome and the risk. This file holds
the rules behind the Depth Contract section of `SKILL.md`. It adds depth
selection only. Map, GPS, and hybrid design selection stays in
[script-integration-framework.md](script-integration-framework.md).

## Accepted outcome

Write three things before any phase runs:

1. What must be true when the work is done.
2. The check that proves it, preferably a script or validator.
3. Who accepts it.

If the check or the acceptor is missing, that gap is missing evidence and pushes
the tier up.

## Choosing the tier

| Input | Low | High |
|-------|-----|------|
| Uncertainty | Scope and trigger phrases are known | Requirements open, no matching skill, triggers unknown |
| Consequence | One skill, reversible, no shared defaults | Shipped to others, safety or authority surface, hard to undo |
| Missing evidence | A deterministic verifier exists and prior art was read | No verifier, or prior art unchecked |

All low: Bounded. Any one high: Standard at least. Two or more high, or a new
ambiguous capability: Full.

Escalate mid-run when a verifier fails, scope widens past the stated outcome, or
an unplanned security or authority surface appears. De-escalating mid-run is
allowed only with a recorded reason.

## Always kept

These do not shrink with the tier:

- Phase 0 triage, so no duplicate skill is created.
- Validators (`quick_validate.py`, `validate-skill.py`, `check_docs_safety.py`).
- Independent review. Full tier and consequential changes use the Phase 4 panel.
  A Bounded edit is reviewed by validators plus the repository gates.
- Human decisions on tradeoffs, authority, permissions, and irreversible
  actions.

## Executor choice

| Step | Executor |
|------|----------|
| Triage score, ecosystem scan, validation, packaging | Existing script |
| Interpreting ambiguous intent, synthesizing a design | Model |
| Tradeoff between costs, authority boundary, shipped default | Accountable human |

Do not ask a model to recompute what `triage_skill_request.py` or a validator
returns.

## Reusing evidence

Each reused finding carries its scope (skill or repository) and its freshness (a
commit SHA or ISO date). It is stale, and must be revalidated, when:

- the scope widens beyond what it covered,
- the touched paths changed since the recorded SHA or date,
- a verifier fails on work that relied on it.

Stale context is re-read and re-checked. It is never silently reused.

## Before and after cases

`tests/evals/skill-scenarios/skillforge.json` holds decision-graded scenarios and
a `before_after` block. Each case compares the prior fixed-depth behavior with
the Depth Contract on four measures: accepted outcomes, human effort, cost, and
latency. A figure nobody measured is `unknown`. The fixtures run offline and
make no model call. A reduction in steps is not reported as an improvement when
the accepted outcome or trust regresses.
