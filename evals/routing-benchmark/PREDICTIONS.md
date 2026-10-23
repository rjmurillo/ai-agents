# Pre-registered predictions for the #5426 routing comparison

Committed before any #5426 result exists. Issue #5426 requires H1 to H4, their
falsification thresholds, and the task classes to be fixed before paid runs.
Nothing below changes after a run starts. A rule that proves wrong is
reported as wrong, and a new rule goes in a new file with a new version.

Version: `predictions-v1`. Corpus: the six #5425 scenarios plus nothing else.
Harnesses: Codex and Claude only. Copilot is out of scope by owner decision on
2026-10-03.

## Task classes (declared before execution)

The class comes from `difficulty` in each `scenario.json`. It is never
reassigned from outcomes.

| Class | Scenarios |
|---|---|
| `ordinary_bounded` | RB-01, RB-04, RB-05, RB-06 |
| `fallback_reasoning` | RB-02, RB-03 |

RB-02 qualifies as fallback work because a correct change spans three modules
with a cross-file invariant. RB-03 qualifies because the cause is found only by
reading the failure report. Both were written that way in #5425.

## Run design

| Item | Value |
|---|---|
| Repetitions per scenario, arm, harness | 3 |
| Order | scenario order RB-01 to RB-06, arms in order A, B, C, D, E, F, repetition index outermost |
| Retry budget | 2 correction rounds, as in the runner config |
| Grader | the #5425 deterministic grader. No model judgment. |
| Eligibility | only rows the #5424 runner plans as `ELIGIBLE_MATCHED` or `ELIGIBLE_UNMATCHED`. A row it rejects is not run and not substituted. |

Per harness the maximum number of runner invocations is 6 scenarios x 6 arms x
3 repetitions = 108 rows. Each row spends at most 1 plan invocation, 1 to 3
worker invocations, and 1 reviewer invocation under arm B, so the row count,
not the process count, bounds the plan. The shared spend cap of 400 paid
invocations binds first. Rows run in the order above and the run stops at the
cap. A row the cap cuts off is reported as `NOT_RUN`.

## Decision rules shared by H1 to H4

- Quality is deterministic acceptance rate over the class. Residual defects
  are failed follow-up checks plus scope violations.
- Non-inferior means: acceptance rate within 1 run in 6 of the comparator on
  the same scenarios, and mean residual defects no higher by more than 0.5 per
  run.
- Materially better economics means: lower mean wall-clock seconds per
  accepted task by at least 25 percent AND lower mean uncached tokens
  (input minus cached, plus output) per accepted task by at least 25 percent.
- Cost basis. Codex and Claude subscription runs report no dollar cost for
  these models, and `_eval_common` carries no per-token rate for the GPT-5.6
  ids. Economics here is latency and tokens, unpriced. A price-weighted claim
  is never made. Where models differ in unit price, a token win alone does not
  show a cost win, so the economics leg is stated as "latency and tokens".
- Evidence floor. A class verdict needs at least 8 runs per arm in that class
  (ordinary: 4 scenarios x 3 repetitions = 12 available; fallback: 2 x 3 = 6
  available). The fallback class never reaches the floor of 8 in one harness,
  so `SUPPORTED_FOR` and `FALSIFIED` on fallback-class claims need the floor
  waived: they require the same direction on both fallback scenarios and on at
  least 2 of 3 repetitions each. Without that, the verdict is
  `INSUFFICIENT_EVIDENCE`.
- A harness failure is not a task failure. It is excluded from rates and
  counted. More than 20 percent harness failures in a cell makes that cell
  `INSUFFICIENT_EVIDENCE`.

## H1: Luna default-worker

Prediction: Luna high beats Sol low on quality-adjusted economics for ordinary
bounded work.

Comparison: arm C against arm A, class `ordinary_bounded`.

- `SUPPORTED`: Luna high is non-inferior on quality and materially better on
  economics.
- `FALSIFIED`: Sol low is non-inferior on quality and materially better on
  economics.
- `INSUFFICIENT_EVIDENCE`: neither, or the evidence floor is unmet.

## H2: Terra conditional fallback

Prediction: Terra high is not generally preferred on ordinary work, and has a
reproducible quality advantage on the declared fallback class.

Comparisons: arm D against arms A and C. Ordinary and fallback classes are
reported separately and never pooled.

- `SUPPORTED_FOR:fallback_reasoning`: on the fallback class Terra high has an
  acceptance rate at least 1 run in 6 higher than both Sol low and Luna high,
  by the fallback evidence rule above, and the ordinary class shows no such
  advantage.
- `FALSIFIED`: on the fallback class neither advantage appears.
- `INSUFFICIENT_EVIDENCE`: otherwise.

Terra is never judged from ordinary work, and fallback scenarios are never
reclassified after a failure.

## H3: Sol-only fan-out

Prediction: arm A is non-inferior on quality and better on economics than arm B.

- `SUPPORTED`: A non-inferior to B on all six scenarios pooled and materially
  better on economics.
- `FALSIFIED`: B has an acceptance rate at least 1 run in 6 higher than A
  AND that gap survives economics, meaning B is not materially worse than A on
  both latency and tokens.
- `INSUFFICIENT_EVIDENCE`: otherwise.

## H4: single-agent deep reasoning

Prediction: arm E beats arm A on some complex task class when latency is not
urgent.

Comparison: arm E against arm A, class `fallback_reasoning`.

- `SUPPORTED_FOR:fallback_reasoning`: E acceptance rate at least 1 run in 6
  higher than A by the fallback evidence rule.
- `FALSIFIED`: A is non-inferior to E on quality and materially better on
  economics on the fallback class.
- `INSUFFICIENT_EVIDENCE`: otherwise.

## Claude harness restatement

H1 to H4 name Sol, Luna, and Terra, which are Codex model families. They are
not testable on Claude as written, and no Claude result may be reported
against them. A Claude run would need its own arm definitions and a #5423
capability record, and neither exists. If the owner defines them, the role
mapping below applies, as a mapping of roles and not of capability:

| Role | Codex | Claude |
|---|---|---|
| frontier parent | gpt-5.6-sol | claude-opus-5-5 |
| default worker | gpt-5.6-luna | claude-haiku-4-5 |
| conditional fallback | gpt-5.6-terra | claude-sonnet-5-5 |

The same decision rules, task classes, and thresholds would apply unchanged.

## Decision output

The strategy decision uses the values in #5426. Each of H1 to H4 gets one
status from the sets above. With fewer than 12 accepted ordinary runs or fewer
than the fallback rule for any compared arm, the decision is
`INSUFFICIENT_EVIDENCE`. A recommendation is published only at the strength
the data supports.

## Amendment 1 (2026-10-04): role prompt names the change surface

Decided by the owner on 2026-10-04 (D31). The predictions, hypotheses H1 to H4,
task classes, thresholds, and decision rules above are unchanged. The version
stays `predictions-v1`. Only the run protocol changes.

What changed. Worker role prompts built by `role_prompt` in
`scripts/eval/_routing_live.py` now end with the scenario's legal change
surface, rendered by `change_surface` from `allowed_scope` in `scenario.json`.
The text lists the allowed paths, and the forbidden paths when the scenario
declares any. Every arm receives the same text for a given scenario. A scenario
with no allowed path fails closed and renders no prompt. Plan and review
prompts edit no source file and carry no surface.

Why. In `results-2026-10-03/`, arms A, B, and C each failed RB-01 with the same
scope violation, an edit to `tests/check_visible_slugify.py`. The prompt said
only "Complete this requirement in the working tree" and never named the legal
change surface. The failure came from the prompt, not from an arm, so it could
not separate arms.

Reporting. The 21 runs in `results-2026-10-03/` used the old prompt. They are
reported separately and are never pooled with runs made after this amendment.
They do not count toward the evidence floor in the decision rules. Every run
after this amendment uses the amended prompt.

Count correction (2026-10-21). The sentence above says "The 21 runs". The 21 is
completed invocations (`results-2026-10-03/README.md`). The directory holds 36
rows, of which 4 were scored and 32 were `HARNESS_FAILED`. No rule changes.

## Amendment 2 (2026-10-20): decision floor and decision mapping

Decided by the owner on 2026-10-20 (D4, D5), before any run under Amendment 1
exists. H1 to H4, the task classes, the thresholds, and the evidence floor of 8
runs per arm in a class (line 58) are unchanged. The version stays
`predictions-v1`. Two rules change: the decision floor, and the mapping from
H1 to H4 to a decision value, which the text above leaves open.

1. Decision floor. This replaces the floor in "Decision output" (lines
   143 to 145). Read literally, "12 accepted ordinary runs" for any compared
   arm needs every one of the 12 available ordinary runs of that arm to be
   accepted, so a single task failure would block any decision. The new floor
   counts scored runs. A scored run is neither `HARNESS_FAILED` nor `NOT_RUN`.
   Each compared arm (A, B, C, D, E) needs 12 scored ordinary runs. Arms A, C,
   D, and E also need the fallback rule: at least 2 scored runs in each
   fallback scenario and a harness failure share of at most 1 in 5 in the
   fallback class. If any arm falls short, the decision is
   `INSUFFICIENT_EVIDENCE`.
2. Decision mapping. The base decision is the first match in this list:
   1. All four of H1 to H4 are `INSUFFICIENT_EVIDENCE`, or the floor is unmet:
      `INSUFFICIENT_EVIDENCE`.
   2. H3 is `FALSIFIED` and H1 is not `FALSIFIED`:
      `ADOPT_ORIGINAL_SOL_LUNA_TERRA_ROUTING`.
   3. H3 is `FALSIFIED` and H1 is `FALSIFIED`: `ADOPT_HETEROGENEOUS_ROUTING`.
   4. H3 is `SUPPORTED` and H1 is `SUPPORTED`:
      `ADOPT_SOL_PARENT_WITH_LUNA_WORKERS`.
   5. H3 is `SUPPORTED`: `ADOPT_SOL_FANOUT`.
   6. Otherwise: `KEEP_CURRENT_POLICY`.

   Then, if the base decision is not `INSUFFICIENT_EVIDENCE` and H2 or H4 is
   `SUPPORTED_FOR:fallback_reasoning`, the published decision is
   `ADOPT_CONDITIONALLY`. The report keeps the base decision and names each
   conditional edge: "Terra high for fallback_reasoning" for H2, and
   "single-agent Sol for fallback_reasoning" for H4.

A case this mapping handles badly is reported as such. It is changed only in a
new versioned file, as lines 5 and 6 require.

## Amendment 3 (2026-10-23): Claude arms

Decided by the owner on 2026-10-23 (D9, D10, D11), before any Claude benchmark
result exists. D9: "ensure you have Claude results". The hypotheses H1 to H4,
the task classes, the thresholds, the evidence floor, and the Amendment 2
decision floor and decision mapping are unchanged. The version stays
`predictions-v1`. This amendment defines the Claude arms that the "Claude
harness restatement" (line 124) said did not exist, and it changes one row of
the table at lines 132 to 136.

1. Role mapping. Haiku 5.5 replaces `claude-haiku-4-5` in the default worker
   row of that table. The reason is one model generation across all three
   roles. The mapping is of roles and not of capability.

   | Role | Codex | Claude |
   |---|---|---|
   | frontier parent | gpt-5.6-sol | claude-opus-5-5 |
   | default worker | gpt-5.6-luna | claude-haiku-5-5 |
   | conditional fallback | gpt-5.6-terra | claude-sonnet-5-5 |

2. Claude arms A to F. Each arm is the Codex arm with Sol read as
   `claude-opus-5-5`, Luna as `claude-haiku-5-5`, and Terra as
   `claude-sonnet-5-5`. Efforts are unchanged. The work packages,
   concurrency ceiling, correction budget, reviewer isolation, and
   fresh-context boundary are the Codex values. They live in
   `scripts/eval/examples/routing-benchmark-config.json`.

   | Arm | Claude definition |
   |---|---|
   | A | Opus 5.5 medium parent, Opus low and medium workers |
   | B | Opus 5.5 medium orchestrator, Haiku 5.5 medium and Sonnet 5.5 high workers, isolated Opus 5.5 medium reviewer |
   | C | Arm A with Haiku 5.5 high for ordinary bounded work |
   | D | Arm A with Sonnet 5.5 high for ordinary bounded work |
   | E | One Opus 5.5 high agent, no subagents |
   | F | Opus 5.5 high plan, then a fresh Opus 5.5 high implementer |

3. The hypotheses as role hypotheses for Claude. The thresholds, floors,
   evidence rules, and the Amendment 2 mapping from H1 to H4 to a decision are
   the ones above, read with the Claude models.
   - H1: default worker. Haiku 5.5 high (arm C) against Opus 5.5 low (arm A),
     class `ordinary_bounded`.
   - H2: conditional fallback. Sonnet 5.5 high (arm D) against Opus 5.5 low
     (arm A) and Haiku 5.5 high (arm C), class `fallback_reasoning`, with
     ordinary work reported apart.
   - H3: Opus-only fan-out. Arm A against arm B, all six scenarios pooled.
   - H4: single agent. Arm E against arm A, class `fallback_reasoning`.

   The decision values keep their names and are read with these roles.
   `ADOPT_SOL_FANOUT` means Opus-only fan-out. `ADOPT_SOL_PARENT_WITH_LUNA_WORKERS`
   means an Opus parent with Haiku workers. The conditional edges read "Sonnet
   5.5 high for fallback_reasoning" and "single-agent Opus 5.5 for
   fallback_reasoning".

4. Results are scored per harness and never pooled. A Codex run and a Claude
   run are never counted in one cell, one verdict, or one decision. The scorer
   reports each harness under its own H1 to H4, decision, and floor, and
   refuses rows from two harnesses in one verdict. This amendment changes no
   Codex verdict. The owner states that the Codex verdicts stay
   `INSUFFICIENT_EVIDENCE` on its partial runs, and no Claude result changes
   them.

5. Run design for Claude. 3 repetitions per scenario and arm, in the order of
   the Run design table: scenarios RB-01 to RB-06, arms A to F, repetition
   outermost. The shared cap is 400 paid invocations, as for Codex. A row the
   cap cuts off is `NOT_RUN`. A usage-limit stop, an auth error, and a stream
   that does not report `apiKeySource: none` are harness failures. They are
   counted and excluded from rates.

6. Cost basis. Claude runs on the operator's subscription login, never an API
   key, and is unpriced. Economics is latency and tokens. Uncached tokens are
   the prompt tokens not read from the cache, plus output tokens, matching the
   Codex measure. No verdict reads `cost_usd`.

7. Effort and eligibility on 2026-10-23. The Claude stream names no reasoning
   effort, so the requested effort is recorded and never confirmed. The #5423
   capability matrix therefore classifies Claude arms A, C, D, and E as
   `UNVERIFIED`, because they require a verified effort override, and
   classifies arms B and F as `ELIGIBLE_UNMATCHED`
   (`evals/harness-capability/claude-2.1.309-2026-10-23.md`). The Run design
   rule applies as written: a row the runner rejects is not run and not
   substituted. H1, H2, and H4 need arms that are rejected, and H3 needs arm A,
   so each stays `INSUFFICIENT_EVIDENCE` on Claude until the matrix classifies
   those arms eligible. Relaxing that evidence rule is the owner's decision and
   would go in a new versioned file.
