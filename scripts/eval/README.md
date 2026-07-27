# Eval Scripts

Behavioral evaluation tools for prompt, skill, and agent changes. Implements ADR-057.

## Quick Start

```bash
# Auto-detect changes and run appropriate evals:
python3 scripts/eval/eval-suite.py --dry-run

# Evaluate a specific prompt change (before/after comparison):
python3 scripts/eval/eval-prompt-change.py \
  --prompt .claude/commands/research.md \
  --scenarios tests/evals/research-scenarios.json \
  --base-ref main \
  --dry-run

# Assess agent definition quality:
python3 scripts/eval/eval-agents.py --agent analyst --dry-run

# Assess skill knowledge integration:
python3 scripts/eval/eval-knowledge-integration.py --skill cva-analysis --dry-run

# Eval rule activation (does the rule fire when conditions hold?):
python3 scripts/eval/eval-rule-activation.py \
  --scenarios tests/evals/rule-scenarios/working-with-legacy-code.json --dry-run

# Detect pairwise skill overlap (are two skills redundant with each other?):
python3 scripts/eval/eval-skill-overlap.py \
  --pairs scripts/eval/examples/example-overlap-pairs.json --dry-run
```

## Scripts

| Script | Purpose | ADR |
|--------|---------|-----|
| `eval-suite.py` | Orchestrator. Detects changes, routes to correct evaluator. | ADR-023 + ADR-057 |
| `eval-prompt-change.py` | Before/after behavioral comparison for prompt changes. | ADR-057 |
| `eval-agents.py` | Agent definition quality assessment (standalone). | Complementary |
| `eval-knowledge-integration.py` | Skill context value measurement (baseline vs enhanced). | Complementary |
| `eval-skill-overlap.py` | Pairwise skill redundancy detection (DISTINCT / OVERLAP / SUBSUMED) for catalog pruning. | Complementary |
| `eval-rule-activation.py` | `.claude/rules/*.md` activation across baseline / description / full mechanisms. | Complementary |
| `analyze-pr-churn.py` | Deterministic commit-churn classification across a PR cohort (degenerate vs control) to evaluate instruction/rule changes against historical PRs. No LLM; core in `_pr_churn.py`. | Complementary |
| `eval-reviewer-asymmetry.py` | Statistical-significance test for `templates/agents/{critic,qa,implementer}.shared.md` reviewer-asymmetry framing. Fisher's exact (verdict-pass) + Mann-Whitney U (findings-count). | Complementary |
| `eval-e2e-delivery.py` | End-to-end delivery eval (plan-rubric proxy). Feeds a vague germ, captures each agent's plan, LLM-judges it against hidden acceptance criteria. Core in `_e2e_delivery_core.py`. | #2859 |
| `eval-model-sweep.py` | Sweep one agent's fixtures across candidate models; scored KEEP_PIN/DROP_PIN verdict with effect size. Core in `_model_sweep_core.py`. | #2840 |
| `optimize-artifact.py` | Held-out-gated edit loop for agents, rules, and hooks. Splits tasks, bounds how many times an edit may be measured against the held-out group, and applies patches. A budgeted comparison, not an access boundary; see the seam section below. Core in `_optimizer_core.py`, scorer adapters in `_optimizer_adapters.py`. | #3422 |
| `_anthropic_api.py` | Shared API utilities (key loading, API calls). | N/A |

## End-to-End Delivery Eval

The routing eval (`eval-prompt-change.py`) scores a single classify-and-route
decision; orchestrator and autoplan both hit the routing ceiling there, which
proves lane-picking, not delivery. `eval-e2e-delivery.py` measures whether an
agent can carry an under-specified ask toward done.

This is harness shape 2 from issue #2859 (the cheaper plan-rubric proxy). It
feeds each agent a deliberately vague germ, captures the plan the agent emits,
and has an LLM judge score that plan against hidden acceptance criteria on
five axes (max 11): `scope`, `completeness`, `process_gates`, `decomposition`,
`correct_stop`.

```bash
# Validate fixtures + resolve agent prompts; no API calls:
python3 scripts/eval/eval-e2e-delivery.py \
    --fixtures scripts/eval/examples/e2e-delivery-fixtures.json --dry-run

# Live run, 3 runs per cell (flakiness protocol), write a report:
python3 scripts/eval/eval-e2e-delivery.py \
    --fixtures scripts/eval/examples/e2e-delivery-fixtures.json \
    --runs 3 --output artifacts/e2e-delivery.json
```

Ground-truth discipline: for the `feature`/`bug` fixtures the hidden criteria
are derived from a real merged PR (see each fixture's `provenance`), so they
are independent of the agent prompts under test. `ambiguous` and
`multi-domain` fixtures are synthetic process probes (stop-and-ask, or
coordinated decomposition) and labeled as such.

Honest limits (printed in every report as `caveat`):

- Plan quality is a proxy for delivery. A high score does not prove the code
  compiles or passes tests; that needs the trace-based shape (#2859 shape 1).
- The fixtures and criteria are single-author curated, so absolute scores are
  directional. Trust relative deltas that clear the run-to-run noise band.
- Same-family judge (the default model judges its own family's output).

`--agents` selects which agents to compare (default `orchestrator,autoplan`);
`--ref` loads an agent prompt from a git ref if it is not on the working tree.

## Reviewer-Asymmetry Eval

`eval-reviewer-asymmetry.py` measures whether the reviewer-asymmetry
framing in the new critic/qa/implementer templates produces a statistically
significant behavioral delta vs the origin/main control versions.

- **Control**: agent template at the chosen git ref (default: `main`).
- **Treatment**: agent template at HEAD (working copy).
- **Trials**: configurable, default 5; production runs use 10.
- **Tests**: Fisher's exact (one-sided) on verdict-pass rate; Mann-Whitney U
  (one-sided) on findings count where the fixture sets `min_findings_count`.
- **Acceptance**: p < 0.05 AND treatment > control, both overall and
  per-agent.

Fixtures live in `evals/reviewer-asymmetry-spike/fixtures/` and follow a
schema that pairs `verdict_options` with optional `min_findings_count` for
continuous metrics. See `evals/reviewer-asymmetry-spike/README.md`.

Cost: ~$0.60 USD for 10 trials × 6 fixtures × 2 conditions = 120 calls.

## Rule Activation Eval

`eval-rule-activation.py` measures whether a `.claude/rules/*.md` file actually
changes agent behavior across three loading mechanisms:

1. **baseline**. Empty system prompt (control).
2. **description**. Only the rule's frontmatter `description` is in the system prompt. Mimics an agent reading `.claude/rules/` and matching descriptions.
3. **full**. Entire rule body in the system prompt. Mimics `@import` from CLAUDE.md or `alwaysApply: true`.

Each scenario × mechanism produces a response that is graded by an LLM judge on
three 1-5 dimensions: `activation_score`, `citation_score`, `behavior_score`.
The eval passes when the best non-baseline mechanism averages ≥3.5 and beats
baseline by ≥0.5. Any judge/API failure forces verdict `FAIL_JUDGE_ERRORS`,
overriding the score-based gate. A scenarios file that contains no positive
cases (only `skip-rule-not-applicable` scenarios) yields `NO_POSITIVE_CASES`,
also a failing verdict because activation cannot be validated by negative
cases alone.

Per-rule scenario files live in `tests/evals/rule-scenarios/{rule}.json`:

```json
{
  "rule_path": ".claude/rules/working-with-legacy-code.md",
  "rule_id": "working-with-legacy-code",
  "scenarios": [
    {
      "id": "S1",
      "desc": "Refactor untested legacy function",
      "input": "Simulated user prompt that should trigger the rule.",
      "expected_signals": ["characterization", "tests before", "seam"],
      "expected_gate": "characterization-tests-first",
      "rationale": "Why the rule must activate here."
    },
    {
      "id": "Sn",
      "desc": "Negative case: well-tested recent code",
      "input": "...",
      "expected_signals": ["existing tests"],
      "expected_gate": "skip-rule-not-applicable",
      "rationale": "Rule should NOT fire."
    }
  ]
}
```

Adding a new rule eval:

1. Write `tests/evals/rule-scenarios/{rule-id}.json` with 3-5 positive scenarios and at least one negative case.
2. Run `python3 scripts/eval/eval-rule-activation.py --scenarios tests/evals/rule-scenarios/{rule-id}.json --dry-run` to confirm the script can parse the rule.
3. Run live (without `--dry-run`) to score. Cost is ~$0.25 per rule (24 calls × ~3500 tokens).
4. Iterate on the rule's `description` field until the `description` mechanism scores within 0.5 of `full`. That is the signal the rule is activatable from frontmatter alone.

## Skill Overlap Eval

`eval-skill-overlap.py` answers a question `eval-knowledge-integration.py`
cannot: are two skills redundant with each other? The knowledge-integration
eval measures a skill against the baseline LLM. The overlap eval measures one
skill against its sibling, so the catalog prune has the second signal it needs.

For each pair `(A, B)` and each prompt, three conditions run: `baseline`
(prompt only), `skill_A` (prompt + A's context), and `skill_B` (prompt + B's
context). An LLM judge scores each response 1-5 against the prompt's expected
answer. The per-direction deltas drive the verdict:

- **DISTINCT**: each skill helps mainly on its own prompts. Keep both.
- **OVERLAP**: both skills cover each other's prompts symmetrically. Fold candidate.
- **SUBSUMED**: one skill covers the other's prompts without reciprocity. Prune candidate.

Phase 1 (Issue #1932) is **explicit pair list only**. No cluster shortcuts, no
full N-squared sweep. The N-squared cost is `N^2 * prompts * 3 conditions *
judge` (~36k calls for 70 skills), so unbounded mode is gated out of scope.

Input is a `cluster.json` with a `pairs` list and a `prompts` map. See
`examples/example-overlap-pairs.json`. The default run cost estimate prints at
run start (API call count, token total, USD estimate).

Dry-run validates the pair file, referenced skill directories, and `--run-id`
before printing the cost estimate. `--run-id` accepts 1-128 characters: letters,
digits, `.`, `_`, and `-`; it must start with a letter or digit and cannot
contain `..`. Pair entries must reference two different skills. Judge responses
that are not valid `{"score": <number>}` payloads fail the run with exit code 3
instead of being averaged into a verdict.

Output lands at `evals/reports/overlap-<RUNID>/`: `matrix.json` (machine
readable per-pair deltas and verdicts) and `REPORT.md` (prune/fold table).

Note on the Issue #1932 Phase 1 pairs: `doc-coverage`, `doc-sync`, and
`session-qa-eligibility` were deleted in the M1 catalog prune (commit
`5c4729345`, #1942). Three of the four named pairs referenced those skills, so
the example file targets the surviving overlapping pairs only
(`memory-enhancement`/`curating-memories`,
`curating-memories`/`exploring-knowledge-graph`).

## Model Sweep Eval

`eval-model-sweep.py` answers a question the pin registry (#2891) cannot: does a
`model:` pin actually beat the harness default, or is it cargo-cult config? For
one agent it runs the existing single-model evaluator (`eval-agent-vs-baseline.py`,
agent variant) once per candidate model, then compares the per-fixture pass rates
across models and emits a scored verdict (Issue #2840, acceptance criterion 2).

```bash
scripts/eval/eval-model-sweep.py \
  --agent security \
  --fixtures evals/security-spike/fixtures \
  --models claude-sonnet-4-6,claude-opus-4-6 \
  --n-runs 3
```

The default model (`claude-sonnet-4-6`) is always added as the comparison anchor.
The metric is the **unweighted mean per-fixture pass rate** over the fixtures that
are stable (non-flaky) for *every* swept model (the shared stable subset). The
same metric drives both the point delta and the CI, so the gate never mixes
estimands. Every non-default candidate is scored against the default; a noisy
top-point-estimate model cannot force a KEEP, nor suppress a solid runner-up. The
verdict:

- **KEEP_PIN**: some candidate leads the default by at least `--min-effect`
  (default 0.05) mean recall AND the paired bootstrap 95% CI on the delta
  excludes 0. Keep that pin and cite the sweep artifact. The strongest such
  qualifier wins.
- **DROP_PIN**: no candidate qualifies (the default ranks first, every lead is
  within noise, or below `--min-effect`). Drop the pin; inherit `auto`.

The report also carries each model's assertion-weighted `agent_recall` from its
single-model report as an informational field, but that value never gates the
verdict. Cohen's d_z is reported as a secondary descriptor only. The comparison
math (paired fixture-id bootstrap, same percentiles as the agent-vs-baseline CI,
computed on the shared stable subset) lives in the pure, unit-tested
`_model_sweep_core.py`. The orchestrator injects a runner (`ModelEvalRunner`), so
the KEEP/DROP decision is testable without API spend.

Two guards keep the verdict honest. Each candidate's bootstrap stream is seeded
from its own model id, so the outcome is independent of `--models` order. When
more than one candidate is swept, the per-candidate CIs are Bonferroni-widened
(the two-sided 5% alpha is split across candidates), so sweeping many models does
not inflate the false-KEEP rate. A sweep with fewer than two shared stable
fixtures is undecidable (the bootstrap CI collapses onto the point delta) and
always DROPs; widen the shared `--fixtures` set to decide.

**Prerequisite (freshness gate):** every swept model must have a pricing rate in
`MODEL_PRICING_RATES_USD_PER_1K_TOKENS` (`_eval_common.py`). The base evaluator
hard-fails on an unpriced model (#2858), so the sweep pre-checks pricing and
exits `2` with an actionable message naming the unpriced models. It does **not**
invent pricing. Today only two `claude-sonnet` ids are priced, so a real
opus/haiku sweep needs a verified pricing entry added first. `--dry-run`
validates inputs and prints the per-model plan with no API calls.

Output is a JSON artifact (`--output`, default under
`evals/{agent}-spike/reports/`) with `schemaVersion`, per-model recall/tokens/
cost, the winner, `recall_delta`, `ci95`, `cohens_d`, `best_candidate_*`, and
the `decision`/`reason`.

## Held-Out-Gated Optimization

`optimize-artifact.py` adds the piece the rest of this directory is missing: a
bound on how many times an edit may be measured against a group before the
measurement stops meaning anything. Every other evaluator here scores an
artifact against its whole eval set and reports the number, so an author who
edits until that number rises has fitted the eval and has no way to know it.

Every other evaluator here scores an artifact against its whole eval set.
`eval-prompt-change.py` compares a prompt before and after an edit on the same
scenarios the author was reading. `eval-agent-vs-baseline.py` scores an agent
against every fixture in its spike directory while the author reads the
failures and rewrites the prompt. Both fit the test set, so an improvement they
report may be memorization rather than a better artifact.

This tool splits the task ids into three groups and keeps them apart:

| Group | Who sees it | Purpose | Default share |
|-------|-------------|---------|---------------|
| `opt` | The optimizing agent | Read failures here, propose edits from them. | The remainder, 0.6 |
| `sel` | The gate | Decides accept or reject. Each decision spends one consultation from a fixed budget. | 0.4 |
| `test` | Nothing yet | Reserved for a final report. **No command scores it**, so today it only shrinks `opt` and `sel`. See ADR-087 Open Requirement 7. | 0.0, opt in with `--test-ratio` |

`--test-ratio` defaults to zero, so out of the box you get two groups and an
empty `test`. That is a concession to this repo's real fixture counts: most
spike directories hold 8 fixtures, where a third group would leave the
optimizing agent 3 tasks to learn from. Set `--test-ratio 0.2` when the set is
large enough to afford it. The 24-fixture analyst set can; an 8-fixture set
cannot.

Size the `sel` group before trusting a verdict. At the 3-task floor a single
task flipping decides the gate, which is close to a coin toss. The gate is
worth running there as a guard against obvious overfit, not as evidence of
improvement. Treat a held-out accept on fewer than about 8 tasks as a weak
signal and say so wherever you cite it.

The split is a deterministic function of the seed and the task-id set, so it
reproduces on any machine and does not depend on input order. Ratios pick exact
counts rather than hash buckets: bucketing can hand a ten-fixture set a
one-fixture gate, which measures nothing.

### Subcommands

| Subcommand | Purpose |
|------------|---------|
| `extract` | Convert an existing scorer's output to `{task_id: bool}`. |
| `split` | Partition task ids into `opt`, `sel`, and `test`. |
| `budget` | Edits allowed at this step, cosine-decayed from `max` to `min`. |
| `score` | Fraction of one group passing. |
| `apply` | Apply bounded patches to an artifact file. |
| `gate` | Decide whether the candidate replaces the incumbent. |
| `buffer-check` | Has this edit already been rejected? |
| `buffer-add` | Record a rejected edit so it is not re-proposed. |

### Covering agents, rules, and hooks

`extract` is what carries the discipline past skills. Each artifact class
already has a scorer; each reports in its own shape, and `extract` converges
them on the one shape the gate reads.

| `--kind` | Input | Task id |
|----------|-------|---------|
| `agent` | An agent eval `report.json` | Fixture id |
| `rule` | `eval-rule-activation.py` scenario output | Scenario id |
| `hook` | `pytest --junitxml` output | Test node id |

Adapters fail closed. A fixture the variant never ran, a scenario whose judge
errored, and a skipped test all score as failures rather than being dropped.
Dropping a task shrinks the denominator, which raises the score, so a silent
omission would read as an improvement.

`--kind rule` does not invert negative cases. `eval-rule-activation.py` builds
the judge prompt so 5 always means the rule behaved correctly, negative cases
included ("5 means the response correctly did NOT activate the rule"), so the
score arrives already normalized and inverting here would double-invert and
punish rules that correctly stay quiet. Including them is still worth doing:
the evaluator's own verdict averages positive scenarios only, so a rule that
fires when it should not is invisible to it and visible here.

### A loop step

```bash
OA=scripts/eval/optimize-artifact.py

# Baseline the incumbent and fix the split once.
uv run --frozen python "$OA" extract --kind agent --input report.json > base.json
FP=$(uv run --frozen python "$OA" split --results base.json --seed run-7 \
    --out split.json | python3 -c "import json,sys;print(json.load(sys.stdin)['fingerprint'])")

# Per step: check the budget, reject a repeat, apply, rescore, gate.
uv run --frozen python "$OA" budget --step 3 --total 12

# Exit 1 means this edit was already rejected, so skip it. Exit 2 means the
# command itself failed and the loop must stop rather than treat a typo in a
# path as a clean finish.
uv run --frozen python "$OA" buffer-check --buffer rejected.json --patches p.json
case $? in
  0) ;;
  1) continue ;;
  *) exit 2 ;;
esac

uv run --frozen python "$OA" apply --file target.md --patches p.json --budget 3

# Rerun the real scorer here, then extract it to cand.json.
uv run --frozen python "$OA" gate --incumbent base.json --candidate cand.json \
    --split split.json --incumbent-fingerprint "$FP" --max-consultations 5
```

Add `--max-p 0.05` when the held-out group is large enough for the tail to
mean something. See "What a live run measured" below for why, and for the
group size at which the bar starts refusing everything.

On reject, revert the file and run `buffer-add` so the same edit is not
re-proposed. On accept, the candidate becomes the incumbent.

### What the gate refuses

A strictly-greater held-out score is the only way to earn an accept. A tie is a
reject, because an edit that did not move the held-out score is churn and churn
on an artifact costs review attention forever.

The gate reads `sel` and only `sel`. There is no flag to point it at another
group, because a gate that can be aimed at the group the author has been
reading is not a gate.

### What the seam does and does not protect

Read this before citing a run of this loop as evidence.

**What it is.** A consultation-budgeted comparison over a public benchmark,
relying on a cooperating optimizer not to inspect task definitions and result
files it can already reach. **It is not held-out validation of unseen tasks.**

Three things make that the honest description rather than an overcautious one:

- **`extract` emits every task's outcome, uncharged.** It takes `--kind`,
  `--input`, and scoring flags. It takes no group argument, so the mapping it
  writes covers `opt`, `sel`, and `test` alike. The documented workflow has the
  optimizer run `extract` itself to build `base.json` and `cand.json`, which
  means held-out outcomes are already in the optimizer's own files before the
  gate is called. Only `score --group` is group-aware, and nothing forces the
  loop through it.
- **Task ids resolve to readable definitions that carry their own grading
  criteria.** `evals/analyst-spike/fixtures/F001.json` holds the input, the
  expected verdict, and the regex the scorer asserts.
  `tests/evals/rule-scenarios/clean-architecture.json` holds the expected
  vocabulary. `tests/hooks/test_dash_guard.py` is the assertion. So naming a
  held-out task is enough to hand-tune for it, and `split` publishes the
  optimize ids by design, from which the complement follows by subtraction.
- **The gate returns diagnostics, not a verdict alone.** Its payload carries
  both scores, both discordant counts, and the p-value. The ledger bounds how
  many times you may ask, not how much each answer tells you.

**What is actually enforced by the mechanism**, and holds whether or not the
optimizer cooperates:

- The consultation count, its cap, its storage path, and the key it is stored
  under are derived from the held-out membership, with two stated exceptions.
  The path's *root* comes from `$EVAL_LEDGER_DIR`, `$XDG_STATE_HOME`, or the
  home directory, and only the filename inside it is membership-derived. The
  cap's *first* value comes from `--max-consultations`, after which it is
  pinned and a later change is refused. So what cannot be moved by a caller
  argument is a budget already in progress; a first invocation still chooses
  its own cap, and an operator with filesystem access can relocate or delete
  the root.
- Concurrent gates against one split serialize on a lock, so a parallel pair
  cannot spend one budget twice.
- The split record is structurally tamper-evident, in two parts because
  neither alone suffices. The fingerprint covers the split's *inputs* (seed,
  task-id set, ratios), which catches an added or removed task but not a task
  moved between groups, since the union it hashes is unchanged by a move. The
  gate also redraws the split from those recorded inputs and compares
  memberships, which catches the move. Both run on every gate.
- `score --group opt` refuses to read any other group.

**What that combination buys.** An author who is trying to improve an artifact,
rather than to defeat the gate, gets a number that has been asked for a bounded
number of times and cannot silently become a number asked a hundred times. That
is the failure this directory actually had. Dwork's reusable holdout
(arXiv:1506.02629) gives the stronger guarantee, but assumes the analyst reaches
the holdout only through the mechanism. Closing that gap needs a trusted
controller that owns task definitions, scoring, and result files, and hands the
optimizer only the optimize group. See ADR-087 Open Requirement 1. Until then,
do not cite a run of this loop as evidence against an adversarial optimizer.

Four further refusals close holes that open once a loop runs many steps:

- **A broken held-out task.** An aggregate win can still contain a task that
  passed before the edit and fails after it. ADR-057 blocks every pass-to-fail
  transition rather than netting it against a gain, so one broken task rejects
  the edit however good the aggregate looks. There is no override flag: ADR-057
  states its gate "has no mechanism to accept a justified regression", and a
  bypass here would be a weaker rule under the same name that an agent driving
  the loop could set without a human seeing the broken task.
- **Moved split.** The split fingerprint covers the seed, the task-id set, and
  the ratios. If it changes, the gate refuses instead of comparing. This blocks
  the cheapest cheat available: an edit loses, so add fixtures and re-roll.
- **Exhausted consultations.** Gating N times against one `sel` group selects
  on it N times, so the gate keeps a budget in a ledger keyed by the held-out
  membership itself, by default under
  `$XDG_STATE_HOME/ai-agents-eval/ledgers/`. Each piece of that budget moved
  off the command line after a review reproduced a way around the previous
  version:

  | Held where | Why not on the command line |
  | --- | --- |
  | Count | `--consultations` defaulted to zero every invocation, so a loop that passed zero each time had an unlimited budget while looking capped. Review reproduced ACCEPT twice under a cap of one. |
  | Cap | `--max-consultations` defaulted to unlimited, so the ordinary invocation had no budget at all, and a caller that did hit the cap could raise it and continue. It is now required, recorded at the first gate, and a later change is refused. |
  | Ledger path | `--ledger PATH` looked like discipline but a missing ledger starts at zero, so naming a fresh path restored the whole budget. |
  | The split path it was derived from | Deriving the ledger path from `--split` only moved that: copy `split.json` to `split2.json` and the fingerprint matches with no ledger beside it. |
  | The inputs the fingerprint covers | The fingerprint covers the seed, task ids, and ratios, which are inputs to the selection rather than its result, and group sizes round. Ten tasks at `--sel-ratio 0.40` and at `0.41` hold out the same four and fingerprint differently, so one group got two budgets. The key is now a digest of the sorted held-out membership. |

  Any two splits that hold out the same tasks share the budget those tasks have
  already spent, whatever ratio or seed produced them. Redrawing with a new seed
  usually does hold out different tasks, and that is a genuinely new group with
  its own budget; the gate is counting gate comparisons against a set of tasks,
  not against a file.

  A consultation is reserved before the held-out group is read and before the
  results are checked for coverage, not when a verdict comes back. A refusal decided from bookkeeping alone (an exhausted budget, a
  stale incumbent fingerprint, a drifted split) reads nothing and costs nothing.
  Everything past that point costs one, including a results file that turns out
  not to cover the group, and including a process killed mid-comparison. Two
  gates cannot race for the last consultation; the read, the comparison, and the
  write happen under a lock keyed by the same held-out group.

  The gate never names a held-out task, and never prints the key either, since
  the key digests the membership and a digest of an enumerable set is that set.
  `score` and `mcnemar_exact` report which ids they could not find, which is the
  right message everywhere else, so the gate asks its own coverage question and
  answers one bit. Not a count: `split` publishes the held-out size, so a count
  would tell a caller how many of the keys it chose to omit were held out.

  None of that hides the held-out task list, and it cannot. `split` publishes
  `opt` in full, the universe is your own results file, and with no test group
  drawn (the default) the held-out group is the complement by plain
  subtraction. The redaction is worth keeping for the case where a test group
  exists, since there the complement spans two groups and the published sizes
  do not say which task is in which. It is not worth describing as a boundary.

  Held-out outcomes do not stay behind that line either. `score --group` is
  group-aware, but `extract` is not, and the workflow above has the optimizer
  run `extract` itself. What the budget bounds is how many times an edit may be
  compared against the held-out group through the gate, which is the loop's
  own **gate comparisons** against that group. It is not a bound on total
  selection pressure, and the difference matters: `extract` and `score` reach
  results without touching the ledger, so an optimizer that inspects its own
  files applies pressure the count never sees. Closing that needs #3452 and a
  controller. Gate comparisons are the quantity multiple-comparison correction
  is about, and it is the one this mechanism actually holds.

  Three things this does not cover, stated rather than implied. The cap is
  whatever positive integer the first call names, so the budget is only as tight
  as that first invocation. The root is relocatable: `$EVAL_LEDGER_DIR` moves
  it, `$XDG_STATE_HOME` moves it, and so does anything that changes the home
  directory, which is how the tests stay isolated and equally how anyone who
  sets one starts over. And a stale lock left by a killed process is reported
  rather than broken, so clearing it by hand is a deliberate act with no
  record.

  ```bash
  optimize-artifact.py gate --incumbent inc.json --candidate cand.json \
      --split split.json --max-consultations 5 --incumbent-fingerprint "$FP"
  ```

  A first run needs no existing ledger; the gate creates it. `--incumbent-fingerprint`
  is required and `score` reports the value to pass, which is the check that
  catches a baseline scored against a split that has since been redrawn.
- **Protected sections.** Text between `<!-- SLOW_UPDATE_START -->` and
  `<!-- SLOW_UPDATE_END -->` is off limits, markers included. Patches carrying a
  fence marker in their text are rejected too, since one could otherwise open a
  fence over the rest of the file or close an existing one.

### What the numbers can and cannot show

Every compared verdict reports `discordant_gain`, `discordant_loss`, and
`p_value`: the counts of held-out tasks that moved fail-to-pass and
pass-to-fail, and the one-sided exact McNemar tail on those counts. Tasks that
did not move carry no evidence about the edit, so they are not in the test.

The `p` is reported always and enforced only when you ask, with `--max-p`. It
is off by default for a reason that is arithmetic, not taste. A held-out group
with three discordant tasks cannot produce a `p` below 0.125 no matter how
one-sided the result, so a conventional 0.05 floor makes the ordinary case
unpassable rather than informative. Read the default as a resolution limit: at
these sizes a single task flip moves the verdict, so a one-step accept is weak
evidence and a run of them is worth more than any single number.

When you do pass `--max-p`, it is the **family** bar, not the per-comparison
one. A budget of five consultations each judged at 0.05 has a family-wise false
accept probability of `1 - 0.95**5`, about 0.226, which is not the number an
operator asking for 0.05 believes they are getting. So the gate spends the bar
across the declared budget by Bonferroni: each comparison is held to
`--max-p / --max-consultations`. The verdict reports both as `max_p` and
`max_p_per_comparison`. Two consequences worth stating plainly. Raising the
budget buys more looks at a stricter bar, never a cheaper one, so there is no
way to buy an accept by declaring more consultations. And the correction makes
the power problem worse, not better: at ten held-out tasks a one-sided exact
McNemar tail needs five one-directional discordant pairs to clear 0.05, and
seven to clear the 0.01 that a budget of five implies. A bar this strict
refuses genuine improvements too. That is the honest trade, and it is why the
flag defaults to absent. Power comes from more tasks or repeated sampling, not
from tuning the bar.

The bar is pinned in the ledger like the consultation cap, and its absence is
pinned as firmly as its presence. A candidate refused at 0.05 cannot be gated
again at 0.1, or with the flag dropped, against the same held-out group. To
change the bar, re-split.

The seam is boolean, so an edit that lifts every held-out task from 0.50 to
0.99 without crossing the threshold scores as no change and rejects as a tie.
That is a real limit of this design, not a rounding artifact. Lower
`--pass-threshold` when the artifact under test moves scores rather than
outcomes.

### Exit codes

Per ADR-035. A reject is exit 1 because it is a decision a shell loop branches
on, not a crash. Every verdict path prints JSON, so a caller that needs to tell
a reject from a broken input reads `decision` rather than inferring from the
code. Argument errors from `argparse` are the exception and print plain text to
stderr, exit 2, as with every other script here.

| Code | Meaning |
|------|---------|
| 0 | Accept, novel patch, or plain success |
| 1 | Reject, already-rejected patch, or a refused patch |
| 2 | Bad arguments, unreadable input, or malformed data |

### Scope

This tool makes no API calls. It decides; the scorers it wraps do the spending.
That is why `--dry-run` applies only to `apply`, and why the whole decision path
is unit-tested without eval budget.

### What a live run measured

The loop above had never been driven by a real model until 2026-07-27. It was
then run end to end against `eval-rule-activation.py` over the seven files in
`tests/evals/rule-scenarios/`, 24 scenarios, scored by `openai/gpt-4o-mini`
through `EVAL_PROVIDER=github`. Read the numbers before trusting an accept.

**The run.** `extract` produced 24 tasks with 12 passing. `split --seed
live-2026-07-27` drew 14 optimize and 10 held out. Acting as the optimizer,
only the 14 optimize ids were read. The chosen edit went to
`.claude/rules/working-with-legacy-code.md`, whose two visible failures both
scored 2.33 with the judge saying the behavior was right but the answer
"lacks the expected vocabulary", while the rule bound its vocabulary to "PR
descriptions and review comments" alone. The edit widened that binding and
added a two-gate summary.

**The verdict.** `gate` returned ACCEPT: held-out 0.6 to 0.8, two discordant
gains, no losses, p=0.25, one consultation of five.

**Why that accept was wrong.** Post-hoc, the edited rule's own four scenarios
had not moved: three still failing, one still passing. Every flip came from a
rule the edit never touched. So the incumbent rule text was restored
byte-for-byte and the identical scorer run again as a null control:

- 13 of 24 tasks changed score at all; 5 crossed the 3.5 pass threshold.
- Mean absolute movement was 0.49 points on the five-point judge scale, with a
  maximum of 3.00.
- The held-out group moved 6/10 to 7/10 on its own.
- Both held-out gains that earned the ACCEPT also flipped under the null run,
  and they were the two largest movements in the whole benchmark: 0.75 to 3.75
  and 1.75 to 3.75.

Gating that byte-identical no-op returned REJECT, but only because the noise
happened to break one task and the no-regression clause caught it. The real
edit and the no-op gained the same two held-out tasks. The verdict was decided
by which way the variance fell, not by the edit.

These are magnitudes observed in a single paired re-run, not an estimated
error rate. One replication cannot put an interval on any of them. It is
enough to establish that the noise is larger than the effect being measured,
which is the only claim made here.

**What changed as a result.** `--max-p` was added so the exact tail the gate
already computed can refuse. Replaying both runs under `--max-p 0.05` turns
the false accept into a reject that names the 0.25 tail. It defaults to absent
because a small held-out group cannot reach a conventional floor, and a bar
nothing can clear is not a gate.

**What did not change, and is the real limit.** At ten held-out tasks a
one-sided exact McNemar tail cannot reach 0.05 without five one-directional
discordant pairs, so on this benchmark `--max-p 0.05` refuses nearly
everything, genuine improvements included. More tasks, or repeated sampling
per task with a majority vote, is what buys power. A different threshold does
not. Until then, treat a single-sample accept on a nondeterministic scorer as
a hypothesis, and run the null control before believing it.

## Scenario File Format

See `examples/example-scenarios.json` for a working template.

```json
{
  "scenarios": [
    {
      "id": "S1",
      "desc": "What this scenario tests",
      "input": "Simulated context the LLM receives",
      "expected_verdict": "STOP",
      "expected_reason_contains": "budget",
      "rationale": "Why this is the expected behavior"
    }
  ]
}
```

Required fields: `id`, `desc`, `input`, `expected_verdict`.
Optional: `expected_reason_contains`, `rationale`.

## Scenario File Locations

| Prompt Type | Scenario Location |
|-------------|-------------------|
| Security benchmarks | `.agents/security/benchmarks/` |
| Other prompt evals | `tests/evals/` |

Convention: for a prompt at `path/to/name.md`, name the scenario file `name-scenarios.json`.

## Flags

All scripts that call the API support `--dry-run` (validate inputs, no API calls) and `--output FILE` (write JSON results). `optimize-artifact.py` makes no API calls; its `--dry-run` is scoped to the `apply` subcommand.

| Flag | Scripts | Purpose |
|------|---------|---------|
| `--dry-run` | All | Validate without API calls |
| `--runs N` | eval-agents, eval-knowledge-integration | Multi-run flakiness detection |
| `--security-critical` | eval-prompt-change | 5 runs, 100% pass required |
| `--base-ref REF` | eval-prompt-change, eval-suite | Git ref for comparison (default: main) |
| `--scope` | eval-suite | Limit to prompts, agents, or skills |
| `--pairs FILE` | eval-skill-overlap | cluster.json with explicit `[skillA, skillB]` pairs and prompts |
| `--run-id ID` | eval-skill-overlap | Override the report directory name (`overlap-<ID>`) |

## Environment

Set `ANTHROPIC_API_KEY` as an environment variable. The scripts also check `.env` files as a fallback.

## References

- [ADR-057](.agents/architecture/ADR-057-prompt-behavioral-evaluation.md)
- [ADR-023](.agents/architecture/ADR-023-quality-gate-prompt-testing.md)
- [Methodology](.agents/testing/prompt-eval-methodology.md)
