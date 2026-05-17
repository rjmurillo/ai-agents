# Skillbook: Evidence-Tiered Agent Policies

The skillbook is a registry of agent behavioral policies whose confidence is
grounded in eval pass/fail outcomes rather than in how a rule was phrased or
how recently it was written.

Every policy in `.agents/` (persona prompts, `AGENT-INSTRUCTIONS.md`, shared
protocols) starts life flat: a rule written down once carries the same weight
as a rule that has survived a hundred runs. The skillbook adds an evidence
tier so an agent can tell the difference and act accordingly.

Implements issue #2030. Lineage: the tiered-evidence model and the
tier-never-decreases discipline are adapted from `DomDemetz/claude-soul`
(lineage: openclaw to claude-soul). This implementation replaces that
project's regex-detected user-sentiment confirmation signal with eval
pass/fail, which is deterministic ground truth.

## Files

| File | Purpose |
|------|---------|
| `policies.json` | The policy registry: every policy, its tier, its evidence. |
| `tensions.json` | Pairs of policies that contradict, with per-context resolution. |
| `workflows.json` | Reusable multi-step workflows with success-rate scoring. |

Each file is validated against a schema in `.agents/schemas/`:
`policy.schema.json`, `tension.schema.json`, `workflow.schema.json`, and
`evidence-entry.schema.json` (referenced by `policy.schema.json`).

## Tier semantics

A policy has a `tier` that reflects how much eval evidence backs it:

| Tier | Promotion gate |
|------|----------------|
| `hypothesis` | Written down, no eval-confirmed application yet. |
| `observed` | At least 1 eval-confirmed application (`confirms >= 1`). |
| `validated` | At least 5 eval-confirmed applications (`confirms >= 5`) AND a contradict rate at or below 10%. |

`confirms` is a weighted sum, not a raw count (see "Evidence weighting"
below). Because any confirmed evidence makes the contradict rate strictly
below 100%, the proposal's "<100% contradict rate" condition for `observed`
is satisfied automatically once `confirms >= 1`.

### Tiers never decrease

A tier only ever rises. `promote` computes the tier the evidence currently
qualifies for, then takes the higher of that and the current tier. The rule
is enforced by an assertion in `promote_policy()`.

When a `validated` policy's contradict rate later climbs back above 10%, it
does not demote. Its `status` flips to `questioning` instead. The tier still
says "this was validated by real evidence"; the status says "the recent runs
disagree, re-examine before relying on it." If the contradict rate falls back
inside the gate, the next `promote` pass returns the status to `active`.

### Status

| Status | Meaning |
|--------|---------|
| `active` | Relied on normally. |
| `questioning` | `validated` tier, contradict rate above the gate. Surfaced, not hidden. |
| `retired` | No longer applied. Hidden by `select`. Set by hand. |

### Worked boundary example

A fresh policy receives 5 eval-confirmed applications. `promote` finds
`confirms = 5`, contradict rate `0%`, and moves it to `validated` / `active`.

A 6th run then contradicts it. The contradict rate becomes `1 / 6` (about
16.7%), above the 10% gate. The next `promote` keeps the tier at `validated`
(tiers never decrease) and flips the status to `questioning`.

## Evidence weighting

`confirms` and `contradicts` are a derived projection of the `evidence`
array. The evidence array is the system of record; the counts are recomputed
from it on every mutation. Each evidence entry is weighted by provenance:

| `context_type` | Weight | Source |
|----------------|--------|--------|
| `external` | 1.0 | Eval pass/fail, incident post-mortems, critic verdicts. Ground truth. |
| `self-referential` | 0.25 | An agent's own claim that it applied the policy. Discounted: an agent grading its own homework is weak evidence. |

`application_count` is the unweighted number of evidence entries.

## Confirmation signal sources (priority order)

1. **Eval pass/fail** (`evals/<spike>/runs/<RUN_ID>/runs.jsonl`) is the
   primary, deterministic signal.
2. `.agents/eval-results/` historical eval outcomes mapped to policies.
3. `.agents/incidents/` post-mortems (an incident contradicts the policy it
   violated).
4. `.agents/critique/` explicit critic-agent verdicts.
5. Self-referential agent claims, marked `context_type: self-referential` and
   weighted 0.25.

## CLI: `scripts/skillbook.py`

```text
skillbook.py status                                    List policies with tier/counts.
skillbook.py confirm <policy-id> --eval <id>           Log an eval-grounded confirmation.
skillbook.py contradict <policy-id> --eval <id> --reason "..."  Log a contradiction.
skillbook.py promote                                   Re-evaluate tiers and statuses.
skillbook.py tension list                              Show detected tensions.
skillbook.py tension prefer <ten-id> <ctx> <pol-id> --eval <id>  Record a resolution.
skillbook.py select <agent> <context>                  Active policies for an agent.
```

`confirm` and `contradict` only append evidence and recompute counts; they do
not change tiers. Run `promote` to re-evaluate tiers and statuses. Both
commands are idempotent on `--eval`: a second call with an eval id already
recorded on that policy is a no-op, so re-running an eval pipeline cannot
double-count.

`select` returns the agent's own policies plus `shared` policies, hides
`retired` policies, surfaces `questioning` policies after `active` ones, and
annotates any policy that wins or yields under a tension in the given context.

Add `--json` to `status`, `tension list`, and `select` for machine-readable
output. Exit codes follow ADR-035: `0` success, `1` logic error, `2` config
error.

## Tension table

When two policies genuinely conflict (`pol-architect-design-first` says
"design before code"; `pol-implementer-spike-first` says "spike to learn
first"), neither is simply wrong. The right choice depends on context.

A `tension` record pairs the two policies and records, per context, which one
wins and the eval evidence behind that resolution:

```json
{
  "id": "ten-design-vs-spike",
  "policy_a": "pol-architect-design-first",
  "policy_b": "pol-implementer-spike-first",
  "preferred_in_context": {
    "bug_repro": {"preferred": "pol-implementer-spike-first", "confirmed_count": 12, "evidence": ["..."]}
  },
  "status": "holding",
  "detected_at": 1778976000
}
```

An agent calls `select <agent> <context>` and is told which policy wins for
the task in front of it, instead of every persona prompt hardcoding its own
`if context == X` ladder.

## Post-eval hook

`.agents/hooks/post-eval.py` is the bridge from eval outcomes to skillbook
evidence. It is not a harness lifecycle hook (it is not one of the
`SessionStart` / `PreToolUse` / `PostToolUse` / `Stop` / `PreCompact` events
in `hooks.yaml`). The eval pipeline invokes it after a run:

```bash
python3 .agents/hooks/post-eval.py \
  --run evals/security-spike/runs/<RUN_ID> \
  --fixtures evals/security-spike/fixtures
```

For each fixture tagged with a `policy_id`, the hook aggregates the fixture's
trial outcomes (the fixture passes when a strict majority of its trials
passed), logs `confirm` evidence for a pass and `contradict` evidence for a
fail, then runs `promote`. Evidence is keyed on `<RUN_ID>::<fixture_id>`, so
re-running the hook on the same run is idempotent.

## Linking an eval to a policy

Add a `policy_id` field to the eval fixture JSON:

```json
{
  "schemaVersion": 1,
  "id": "F001",
  "policy_id": "pol-security-vuln-first",
  "input": "..."
}
```

`evals/security-spike/fixtures/F001.json` is tagged this way as the worked
example. The eval runner ignores fields it does not recognize, so tagging a
fixture does not affect the run itself.

## Adding a new policy

1. Pick an id of the form `pol-<owner>-<short-name>` (lowercase, hyphenated).
2. Add a policy object to `policies.json` with `tier: "hypothesis"`,
   `status: "active"`, empty `evidence`, zeroed counts, `version: 1`, and a
   `source` naming the document the policy came from.
3. Increment `meta.total_discovered`.
4. Run `python3 scripts/validation/validate_skillbook.py` and confirm it
   passes.
5. Optionally tag an eval fixture with the new `policy_id` so the policy can
   start accruing evidence.

A new policy always starts at `hypothesis`. It only rises once evals confirm
it. Do not hand-edit `tier`, `confirms`, `contradicts`, or `application_count`;
those are derived and are recomputed by `confirm` / `contradict` / `promote`.

## Validation

`scripts/validation/validate_skillbook.py` validates all three registry files
against their schemas and runs referential-integrity checks (derived counts
match the evidence, cross-references resolve, tension resolutions name a
paired policy). `.github/workflows/skillbook-validation.yml` runs it on every
PR that touches the skillbook.

## Out of scope for v1

- In-session policy enforcement (would need agent-loop integration).
- Auto-discovery of policies from session transcripts.
- Cross-repo policy sharing.
- Confidence-weighted ranking in `select` (v1 uses simple "active first,
  questioning surfaced, retired hidden").
