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
