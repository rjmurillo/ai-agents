# Decision Brief Protocol

Detail for the `decision-question` skill. Load it only when the routing gate in
`SKILL.md` says ask. The always-on rule `voice.md` points here and does not
carry this content.

## The eight fields

The rendered syntax follows the harness `AskUserQuestion` tool. Do not invent a
new UI contract.

1. **Stable decision ID.** `D1`, `D2`, and so on when more than one decision may
   exist. IDs survive split chains so a later answer names the original
   question. Never renumber an unresolved decision.
2. **Decision statement.** One sentence: what must be decided now. Do not bury
   it in background prose.
3. **Why it matters now.** The blocking consequence or material tradeoff. Cut
   background that does not change the choice.
4. **Distinct options.** At least two materially distinct paths, each with
   enough consequence to choose. Each presented page carries 2 to 4 (see "The
   harness bound"); more options become a split chain. A cosmetic rewrite of another option fails the
   distinct check.
5. **Recommendation.** Recommend an option when evidence and delegated judgment
   support one, and give the load-bearing reason. When they do not, set
   `no_recommendation` and say so. Do not manufacture a preference.
6. **Hold.** Offer `Hold` only when deferring is legitimate. A hold keeps the
   decision ID and records the event or evidence that reopens it. It is not an
   escape hatch for a decision that blocks work now: leave `allow_hold` false.
7. **Dependencies and split chains.** See below.
8. **Completeness check.** See below.

## The harness bound

`decision_question.py` pins what the Claude Code `AskUserQuestion` input schema
accepts, read from the Claude Code 2.1.296 binary:

| Limit | Value |
|-------|-------|
| Questions per call | 1 to 4 (`MAX_QUESTIONS_PER_CALL`) |
| Options per question | 2 to 4 (`MIN_PRESENTED_OPTIONS`, `MAX_PRESENTED_OPTIONS`) |
| `Other` free-text choice | Added by the tool; not counted, never listed as an option |

The schema text calls these hard constraints and says to split into multiple
calls rather than exceed them. This skill asks one decision per call, so the
question bound holds by construction. `Hold` and the continuation entry each
occupy one of the 4 presented slots.

When a harness reports a different cap, read it from that harness's tool schema,
pass it as `--max-options`, and record the source. Do not hard-code a remembered
number. The engine needs a cap of at least 3 to paginate and keep a real choice.

## Split chains

- **More options than the bound.** `plan_prompt_pages` paginates. Each non-final
  page ends with a `_more` entry ("See more options"). When Hold is allowed,
  every page also ends with `_hold`, so Hold is never hidden on a later page.
  The final page holds at least 2 entries by construction: the engine only
  splits while more options remain than the final page can hold, so the
  remainder is never a single option. Six options at a cap of four
  become `[o1, o2, o3, more]` then `[o4, o5, o6]`.
- **Paging.** The engine returns every page plus `page_index` and `page`, the
  entries to present now. When the user picks `_more`, do not record it under
  `answers`. Set `paging` to `{"D1": 1}` (the count of `_more` picks) and rerun;
  the same decision ID returns its next page. Record a real pick under
  `answers`. A count past the final page is malformed (exit 1).
- **Dependent decisions.** Ask the earliest load-bearing decision first. Its
  answer prunes impossible later decisions and filters options that stopped
  being reachable. Express a dependency as `requires` on a decision or on an
  option: a map of earlier decision ID to the answer that keeps it alive.
  `{"D1": "cloud"}` keeps D2 only when D1 was answered `cloud`. A decision whose
  option waits on an unanswered or held prerequisite is deferred, so the user
  never sees a question with an alternative hidden. If an earlier answer filters
  out the recommended option, the engine returns `revise_recommendation` (exit
  2) with the `remaining_options`; pick one of them or set `no_recommendation`,
  then rerun. Decision IDs must be unique within a brief.

Chain states in the output: `deferred` lists decisions waiting on an unanswered
or held prerequisite; `pruned` lists decisions an answer made irrelevant.

## Hold

Pass a Hold answer as the value `_hold` under `answers`. The engine then:

- keeps the decision ID and reports it under `held` with its reopen condition;
- defers (does not prune) every decision that requires it, because the
  prerequisite is unresolved, not answered otherwise;
- reports `status: held` when nothing else is actionable.

Reopen the decision when the stated condition occurs, by rerunning without the
`_hold` answer.

## Completeness check

`missing_brief_fields` returns gaps; an empty list is complete. It flags a
missing statement or "why now", fewer than two options, duplicate labels, an
option with no consequence, a reserved option ID, a missing recommendation
(unless `no_recommendation` is set), a recommendation naming an unknown option
or lacking its reason, and a Hold offer with no reopen condition.

The check is a deterministic list, not a score. `decision-rigor` owns scored
review after a decision artifact exists.

## Before asking on a high-cost choice

Set `irreversible` and `weak_evidence` in `context` when the choice is costly to
reverse and the evidence is thin. The output then lists `pre_ask_review`. Run
`decision-critic` or `pre-mortem` first, fold what they find into the options,
then ask. Skip both for ordinary decisions.

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
        {"id": "redis", "label": "Redis", "consequence": "Auth check drops to about 2ms; adds a second store to operate."},
        {"id": "postgres", "label": "Postgres", "consequence": "One store to operate; auth check stays near 40ms."}
      ],
      "recommendation": "postgres",
      "recommendation_reason": "Traffic is far below the point where 40ms matters; one store lowers operating load.",
      "allow_hold": true,
      "hold_reopen_condition": "Reopen if p99 auth latency exceeds the 25ms SLO in staging."
    }
  ]
}
```

`context` flags the agent sets before the gate runs: `material_decision`
(required to ask), and the skip flags `task_terminal`, `delegated`,
`policy_mandated`, `acceptance_criteria_determined`,
`implementation_detail_authorized`, `resolvable_by_evidence`. A skip flag wins
over `material_decision`.
