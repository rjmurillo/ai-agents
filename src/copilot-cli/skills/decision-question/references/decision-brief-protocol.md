# Decision Brief Protocol

Detailed procedure for the `decision-question` skill. Loads only when a genuine
decision brief is needed. The always-on router in `.claude/rules/voice.md`
points here; it does not carry this content.

## The eight semantic fields

Each decision in a brief carries these fields. The rendered syntax follows the
current harness `AskUserQuestion` structure and existing repository conventions
(see `voice.md`). Do not invent a new UI contract.

1. **Stable decision ID.** A compact identifier (`D1`, `D2`, ...) when more than
   one decision may exist. IDs survive split chains so a later answer can refer
   to the original question without ambiguity. Never renumber an unresolved
   decision into a new ID.
2. **Decision statement.** One sentence naming what must be decided now. Do not
   bury the decision in background prose.
3. **Why it matters now.** The blocking consequence or material tradeoff. Omit
   generic background that does not change the choice.
4. **Bounded options.** Materially distinct paths, not cosmetic rewrites, each
   with enough consequence to choose. Respect the harness maximum (see below).
5. **Recommendation.** Recommend an option when evidence and delegated judgment
   support one, and give the load-bearing reason. When evidence does not support
   a preference, say so rather than manufacturing one. Do not fabricate
   confidence.
6. **Hold/defer.** When deferring is a legitimate choice, offer it explicitly as
   `Hold` or `Defer`. A hold preserves the unresolved decision and records the
   future evidence or event that reopens it. Do not use `Hold` as a generic
   escape hatch when a decision is required now.
7. **Dependency and split-chain behavior.** See below.
8. **Completeness check.** See below.

## The harness option bound

`scripts/decision_question.py` encodes the bound as `MAX_PRESENTED_OPTIONS`,
default `4`, with `HARNESS_LIMIT_OBSERVED = False`. The GitHub Copilot CLI
non-interactive agent environment exposes no `AskUserQuestion`/`ask_user` tool
in the agent tool schema, so the per-prompt option cap could not be observed at
runtime here. The bound is UNVERIFIED and configurable. When you run inside a
harness that does expose the tool, read the real cap from the tool schema and
pass it via `--max-options`, then update the pinned constant and flip
`HARNESS_LIMIT_OBSERVED` with the observed source.

Do not hard-code a remembered platform number as fact. Encode the observed
value or state that it is unverified.

## Split-chain behavior

When more options exist than the bound, or later decisions depend on earlier
answers, split into a chain rather than overflowing one prompt.

- **Over the option bound.** `plan_prompt_pages` paginates deterministically.
  Every non-final page reserves one slot for a continuation sentinel so the user
  can advance; the final page holds the remainder. No page exceeds the bound.
  Six options at a bound of four become `[o1, o2, o3, more]` then `[o4, o5, o6]`.
- **Dependent decisions.** Ask the earliest load-bearing decision first. Use its
  answer to prune impossible or irrelevant later questions and to recompute the
  surviving options. `prune_chain` drops a decision whose prerequisites are
  unmet and filters options that are no longer reachable. `next_decision`
  returns the earliest unanswered decision whose prerequisites hold.

Express a dependency two ways in the brief JSON:

- `Decision.requires`: a map of prior decision ID to the answer that keeps this
  decision alive. `{"D1": "cloud"}` prunes `D2` unless `D1` was answered
  `cloud`.
- `Option.requires`: the same map on a single option, so a later decision keeps
  only the options still reachable under the recorded answers.

## Completeness check

Before asking, verify the brief is decision-complete: the user can choose
without reconstructing hidden assumptions. `missing_brief_fields` returns the
gaps; an empty list means complete. It flags a missing statement, missing
"why now", fewer than two options, non-distinct option labels, any option with
no consequence, a missing or unsupported recommendation (unless an explicit
no-recommendation stance is set), a recommendation that names an unknown option,
and a hold offer with no reopen condition.

Use the deterministic checklist, not a pseudo-precise score. `decision-rigor`
owns scored review after a decision artifact exists; do not invent a numeric
score here for appearance.

## Worked example

```json
{
  "context": {"material_decision": true},
  "decisions": [
    {
      "id": "D1",
      "statement": "Choose the session store for the new auth service.",
      "why_now": "Blocks the auth service skeleton; the store shapes every read path.",
      "options": [
        {"id": "redis", "label": "Redis", "consequence": "Auth check drops to ~2ms; adds a second store to operate."},
        {"id": "postgres", "label": "Postgres", "consequence": "One store to operate; auth check stays ~40ms."}
      ],
      "recommendation": "postgres",
      "recommendation_reason": "Traffic is well under the point where 40ms matters; one store lowers operational load.",
      "allow_hold": true,
      "hold_reopen_condition": "Reopen if p99 auth latency exceeds the 25ms SLO in staging."
    }
  ]
}
```

## When NOT to build a brief

The routing gate in `SKILL.md` is the authority. Restated: delegated choice,
policy-mandated path, acceptance criteria already determine it, implementation
detail within authorized scope, resolvable by reading evidence, or the task is
already terminal. In any of these, act within authorization and emit no
question.
