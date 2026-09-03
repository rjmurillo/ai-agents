# Eval Scripts

Behavioral evaluation tools for prompt, skill, and agent changes. Implements ADR-057.

## Quick Start

```bash
# Auto-detect changes and run appropriate evals:
python3 scripts/eval/eval-suite.py --dry-run

# Evaluate a specific prompt change (before/after comparison):
uv run python scripts/eval/eval-prompt-change.py \
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

# Validate real Claude and Copilot CLI parity fixtures without model calls:
uv run python scripts/eval/eval_runtime_parity.py --dry-run
```

## Providers

`--provider` selects the transport. Most take an API key; one does not.

| Name | Transport | Credential |
|------|-----------|------------|
| `anthropic` (default) | urllib, dependency-free | `ANTHROPIC_API_KEY` |
| `anthropic-sdk` | `anthropic` package | `ANTHROPIC_API_KEY` |
| `openai`, `codex` | `openai` package | `OPENAI_API_KEY` |
| `github`, `github-models` | `openai` package, Models base URL | `GITHUB_TOKEN` |
| `copilot`, `copilot-cli` | GitHub Copilot CLI subprocess | none, reuses `copilot` auth |

Prefer `copilot-cli` when the question is "does this change help the models we
actually run." It costs no separate API billing and reaches the ids this
repository's owner works in. The confirmed panel is
`scripts/eval/panels/owner-copilot-cli.json`:

```bash
python3 scripts/eval/eval-model-panel.py \
  --agents orchestrator \
  --panel-config scripts/eval/panels/owner-copilot-cli.json
```

Three things about `copilot-cli` that will cost you a run if you miss them:

- **It runs in an empty temp directory, deliberately.** The CLI loads
  `AGENTS.md`, `CLAUDE.md`, and `.github/instructions/**` from its working
  directory. In this repository those files are usually the variable under
  test, so running from the repo root would put the treatment into the control
  cell and quietly destroy the comparison.
- **It is a prompt-only transport.** It passes prompt text through ACP and
  disables custom instructions, tools, and built-in MCP servers. It does not
  measure project instruction loading, custom-agent frontmatter, or real tool
  behavior. Use `eval_runtime_parity.py` for those questions.
- **Do not compare its scores to an HTTP provider's.** The Copilot CLI system
  prompt remains present even when custom instructions are disabled. Same
  reasoning ADR-058 already applies to cross-provider comparison.
- **Do not use the CLI's reported token counts as a measurement.** They are
  non-monotonic: the same trivial prompt reported 109.3k tokens from `/tmp` and
  95.9k from inside the repo, because the figure folds in tool definitions and
  cache accounting. For byte and token budgets use
  `scripts/validation/instruction_budget.py`, which is deterministic.

It ignores `max_tokens`, `temperature`, and `seed`, because the CLI exposes no
sampling controls. Fixtures still run unchanged; if you need sampling
determinism, use an HTTP provider. `COPILOT_CLI_BIN` and `COPILOT_CLI_TIMEOUT`
override the executable and the default 900s timeout.

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
| `eval_runtime_parity.py` | Run the same fixture through real Claude and Copilot CLIs with isolated agent profiles, resolved-model checks, traces, and deterministic controls. | #4853 |
| `optimize-artifact.py` | Held-out-gated edit loop for agents, rules, and hooks. Splits tasks, bounds how many times an edit may be measured against the held-out group, and applies patches. A budgeted comparison, not an access boundary; see the seam section below. Core in `_optimizer_core.py`, scorer adapters in `_optimizer_adapters.py`. | #3422 |
| `_anthropic_api.py` | Shared API utilities (key loading, API calls). | N/A |

## Real CLI Runtime Parity

`eval_runtime_parity.py` answers a different question from API and ACP prompt
evals. It loads generated agent artifacts through each CLI's project-agent
mechanism, then runs the same fixture request through both binaries.

```bash
uv run python scripts/eval/eval_runtime_parity.py \
  --fixtures scripts/eval/examples/runtime-parity-fixtures.json \
  --model claude-opus-4.6 \
  --output artifacts/runtime-parity/report.json
```

Each fixture declares one Claude agent, one Copilot agent, deterministic
assertions, and positive and negative controls. The runner creates a nested git
repository per harness; its project profile contains only the selected agent. Claude uses an
isolated config directory, project settings, and an empty MCP configuration.
Copilot uses an isolated `COPILOT_HOME`, disables custom instructions, and
disables built-in MCP servers. A sentinel instruction is placed on each
excluded profile surface; any leak fails the run. The fixture request is passed
as the non-interactive prompt to both CLIs. Reports redact that argv field.
Fixture requests are visible to local process inspection while a CLI runs.
Treat fixture text as public test data. Never place credentials in it.

Reports include:

- CLI versions and the requested model;
- resolved model ids, with exact mismatch failure before later fixtures run;
- SHA-256 hashes for both installed agent artifacts and the fixture request;
- raw JSONL stdout, stderr, final response, tool events, and subagent events;
- per-assertion verdicts labeled `Claude runtime` or `Copilot runtime`;
- `prompt-only` positive and negative control results.

The checked-in suite covers phase resume, reversible tool execution,
consequential choice handling, and QA rejection of 16 valid artifacts against
49 promised. `--dry-run` validates paths, assertions, controls, and CLI
versions without sending a model request.

### Completion-Tail Regression Fixtures

`tests/evals/completion-terminal-runtime-fixtures.json` is a second fixture
corpus for the same runner, covering the completion-tail audit
(`.claude/rules/voice.md`) and the task-completion terminal predicate
(`.claude/rules/builder-ethos.md`) added by issue #5404: a completed response
must not append an unsolicited continuation offer, an out-of-scope finding
found after the task is terminal must be stated declaratively rather than as
an opt-in question, and a real blocking decision must still be askable.

```bash
uv run python scripts/eval/eval_runtime_parity.py \
  --fixtures tests/evals/completion-terminal-runtime-fixtures.json \
  --model claude-opus-4.6 \
  --output artifacts/runtime-parity/completion-terminal/report.json
```

Read the file's own `_scope_note` field before treating a clean run as proof
the audit works in general. These assertions are `regex`/`not_regex` checks
for the prohibited-phrase list voice.md names as fixtures ("Want me to ...?",
"Would you like me to ...?", and similar). They are a regression backstop, not
the semantic authority: a response can reopen an interaction without using any
of those exact strings, and using one of them inside a genuine blocking
question is not itself a defect. A model-graded assertion kind that judges
whether a response actually reopens an interaction, with recorded grader
provider/model and UNAVAILABLE handling when the grader itself cannot run, is
not implemented by this fixture file or by the assertion kinds in
`_runtime_parity.py` (`regex`, `not_regex`, `file_equals`, `file_absent`)
today; that grading capability is deferred follow-up work, not part of this
change. `--dry-run` still validates the fixture schema and both CLI versions
without a model call, and exits 3 (external/unavailable) rather than a false
pass when a required CLI binary is not installed.

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

`eval-rule-activation.py` measures whether a `.claude/rules/*.md` rule or a
skill reference actually changes agent behavior across three loading
mechanisms:

1. **baseline**. Empty system prompt (control).
2. **description**. Rules expose only their frontmatter `description`. Skill references expose only the umbrella skill catalog entry first, then the skill router must select the reference before the response can use it. Mimics progressive disclosure through the real front door.
3. **full**. Entire rule body, or skill router plus selected reference body, is in the system prompt. This is a diagnostic ceiling only.

Each scenario × mechanism produces a response that is graded by an LLM judge on
three 1-5 dimensions: `activation_score`, `citation_score`, `behavior_score`.
The eval passes only when the `description` mechanism averages ≥3.5 and beats
baseline by ≥0.5. `full` cannot rescue a failed description route. Any judge/API failure forces verdict `FAIL_JUDGE_ERRORS`,
overriding the score-based gate.

Both pools are required, and a file missing either one is refused. A file with
no positive case (only `skip-rule-not-applicable` scenarios) yields
`NO_POSITIVE_CASES`, because activation cannot be validated by negative cases
alone. A file with no negative case yields `NO_NEGATIVE_CASES`, because the
restraint floor would then be computed over an empty pool: it cannot fail
there, and a clean positive result would read as a clean run, certifying
restraint the run never measured. Both are refused earlier and more cheaply
than that. Validation rejects an empty scenario list, a file with no positive
scenario, and a file with no negative scenario before any API call, so the pull
request dry run catches all three for free. The verdicts remain because replay
and direct callers reach the aggregation step without passing through the
scenario loader, and a gate that only one path enforces is a gate with a hole
in it.

The process exit code names which kind of thing went wrong: 0 clean, 1 a rule
that underperformed, 2 a configuration problem, 3 an external or API failure,
4 a credential that could not be loaded.
`NO_POSITIVE_CASES` is a 2, not a 1. It reports that the scenario file cannot
validate activation and says nothing at all about the rule, so reporting it as
a rule failure would attach a verdict to a population the run never measured.
`NO_NEGATIVE_CASES` is a 2 for the same reason, one pool over.
A run reduces the verdict codes with `max()`, so the worst outcome across all
targets decides the exit and adding a target can never improve it.

Exit 4 sits outside that reduction. It is returned before the first target is
read, when `_load_api_key` cannot produce a credential, so no scenario has been
measured and there is nothing to reduce against. Reading 4 as the top of the
`max()` ordering would invert what it reports: 3 says the run reached the API
and the API failed, while 4 says the run never got that far. A caller that
branches on these should treat 4 as "nothing ran" rather than as a worse 3.
A dry run skips credential loading entirely and so cannot return 4.

Per-rule or per-reference scenario files live in `tests/evals/rule-scenarios/{rule}.json`:

`rule_id` names the population every number in that file is published under, and one run refuses two files that claim the same id rather than letting the second overwrite the first. Omitting it is safe but not free: a reference target then defaults to the reference filename, so two references under one skill router stay distinct only as long as their filenames do. When present, `rule_id` and `skill_id` MUST be non-empty strings. The published record is a JSON object keyed by this value, and JSON keys are strings, so a declared `1` and a declared `"1"` are two distinct keys in memory that clear the duplicate check and then collapse to one key on serialization, dropping a measured target from the record without a word. The loader refuses the type before any API call rather than losing the result after all of them.

```json
{
  "skill_path": ".claude/skills/software-engineering-library/SKILL.md",
  "reference_path": ".claude/skills/software-engineering-library/references/working-with-legacy-code.md",
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

Adding a new activation eval:

1. Write `tests/evals/rule-scenarios/{rule-id}.json` with at least one positive scenario and at least one negative case. The harness enforces that both pools are non-empty before it spends anything, so a file missing either fails the dry run rather than reaching a live scoring run. Aim for 3 to 5 positives: fewer makes the average a description of one or two observations, more mostly buys API spend. That range is guidance, not a check. Most files in the tree carry two positives, so enforcing a floor of three would refuse the corpus every published result was measured on.
2. Give every scenario an `expected_gate`. The harness refuses a file where one is missing, because that string picks the judge rubric and the pool: an unreadable gate would grade a negative case against the positive rubric and then average it into the positive pool. `skip-rule-not-applicable` is the one value that marks a negative case, and any near miss of it in the `skip-rule` namespace is refused rather than scored as a positive.
3. Use `rule_path` for always-on rules, or `skill_path` plus `reference_path` for progressive-disclosure references.
4. Run `uv run python scripts/eval/eval-rule-activation.py --scenarios tests/evals/rule-scenarios/{rule-id}.json --dry-run` to confirm the script can parse the target.
5. Run live (without `--dry-run`) to score. Skill-reference targets add one route call per scenario before response scoring.
6. Iterate on the rule or skill `description` field until the `description` mechanism passes on its own. Treat `full` as ceiling diagnostics, not as a passing route.
7. Read the `Routing:` caveat before accepting a `description` pass. One skill router fronts every sibling reference, and a sibling resolves for your target as readily as the target does. That caveat counts the positive cells whose router never opened the reference under test, so a pass reported beside a nonzero count is partly a measurement of some other reference.

### Software Engineering Library Rollback Gate

ADR-088 moved these eight book-derived references behind `software-engineering-library`:
`clean-architecture`, `domain-driven-design`, `enterprise-patterns`, `refactoring`,
`release-it`, `philosophy-of-software-design`, `data-intensive-applications`, and
`working-with-legacy-code`.

Owner: `agent-qa`.

Cadence: weekly Monday 06:30 UTC through
`.github/workflows/software-engineering-library-activation.yml`, with a
`pull_request` dry-run wiring gate for changes to the skill, fixtures, eval script,
or workflow.

Persistent state lives in the GitHub Actions cache at
`.eval-state/software-engineering-library-activation-state.json`. The state records
one entry per moved reference with `consecutive_activation_failures`,
`last_verdict`, `last_run_id`, and `last_checked_at`. `FAIL_THRESHOLD`,
`FAIL_NO_DELTA`, `NO_POSITIVE_CASES`, and `NO_RESULT` increment the rollback streak.
`FAIL_JUDGE_ERRORS` is treated as an external eval failure and does not increment
the activation rollback streak.

The measurement verdicts carry no evidence about the rule, so they are absent
from that list on purpose. `FAIL_ROUTE_MISSED_TARGET` means at least one positive
cell scored on a reference the run never opened: one skill router fronts many
sibling references, and a sibling resolves for any target, so the score measures
content the target did not supply. Counting it would retire a rule for the
harness's routing imprecision. The miss is counted only on the mechanisms the
target can actually reach, which for a routed target excludes `full`: that
treatment is force-injected, no deployment performs it, and its scores are
already dropped from every average, ranking, and gate, so letting a miss there
decide the run would hand the verdict to a mechanism the target cannot reach.
`FAIL_POSITIVE_INCOMPLETE`,
`FAIL_NEGATIVE_INCOMPLETE`, and `FAIL_OVER_ACTIVATION` are excluded for the same
reason. Fix the routing or the reference, then re-run.

`NO_NEGATIVE_CASES` is excluded too, which reads as an inconsistency next to
`NO_POSITIVE_CASES` on that list until you ask what the rollback does. Rollback
restores the reference to the always-on rule surface. That remedies "the run
cannot show the skill activates", so `NO_POSITIVE_CASES` counts. It cannot
remedy "the run cannot show the skill restrains", because an always-on rule is
the least restrained state available: rolling back would move the reference
further from what the missing pool was supposed to measure. Add the negative
scenario instead.

The workflow runs all eight scenario files live on the weekly schedule and feeds
`activation-results.json` into
`scripts/eval/software_engineering_library_activation_gate.py`. A reference that
reaches two consecutive activation failures trips the rollback threshold.

When the threshold trips, the workflow uploads the eval report, opens or updates a
rollback tracking issue, and fails the repository gate. The restoration PR must
restore the failing book reference to the always-on rule surface or strengthen the
skill trigger and scenario coverage. It must include the latest gate report and pass
this workflow before merge.

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
| `test` | `report`, once | The final number, read after the loop converges. `report` scores it once and refuses every read after that. It never gates. | 0.0, opt in with `--test-ratio` |

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
| `extract` | Convert an existing scorer's output to the results envelope. |
| `split` | Partition task ids into `opt`, `sel`, and `test`. |
| `budget` | Edits allowed at this step, cosine-decayed from `max` to `min`. |
| `score` | Fraction of one group passing. |
| `apply` | Apply bounded patches to an artifact file. |
| `gate` | Decide whether the candidate replaces the incumbent. |
| `report` | Score the `test` group once, after the loop is done. |
| `buffer-check` | Has this edit already been rejected? |
| `buffer-add` | Record a rejected edit so it is not re-proposed. |

### Covering agents, rules, and hooks

`extract` is what carries the discipline past skills. Each artifact class
already has a scorer; each reports in its own shape, and `extract` converges
them on the one shape the gate reads.

| `--kind` | Input | Task id | Corpus identity |
|----------|-------|---------|-----------------|
| `agent` | An agent eval `report.json` | Fixture id | `fixture_set_sha` |
| `rule` | `eval-rule-activation.py` scenario output | Scenario id | none published |
| `hook` | `pytest --junitxml` output | Test node id | none published |

`extract` writes an envelope, not a bare mapping:

```json
{
  "schema": "optimizer-results/1",
  "corpus": "26136df314d6c7b57fb85b8557440ac61d49c8728529f3040b930c8ff7ca02ef",
  "results": {"A001": true, "A002": false}
}
```

`corpus` answers "which task set was this scored against", as the producer's
sha256 hex digest of that set, and `gate` refuses a pair that does not agree on
it. The reader accepts exactly sixty-four lowercase hex characters, or `null`;
a truncated, upper-case, or otherwise short value is a config error and exits
2, because a value that is not a whole digest cannot be compared and would
report a verified match it never made. `split` pins the value it was drawn from
so the answer cannot be stripped back out. Only the agent path has a source for
it today, so the other two write `null` and the gate reports the comparison as
unverified rather than pretending it checked. A bare `{task_id: bool}` file
still reads, as an unknown corpus.

Adapters fail closed. By default a fixture the variant never ran and a skipped
test both score as failures rather than being dropped; `extract --kind hook
--on-skip exclude` opts out for plain skips. Dropping a task shrinks the
denominator, which raises the score, so a silent omission would read as an
improvement.

That is the default and not the only policy. `extract --kind hook` takes
`--on-skip`, which is `fail` above and `exclude` to drop a skipped test from the
mapping instead. Reach for `exclude` only when the skips are static, because
dropping a task is not free. A conditionally skipped test changes the task-id
set between runs, and the split was drawn once from the full set. If the dropped
id landed in the held-out group, the gate charges a consultation, reports
`REJECT` at exit 1, and says `compared: false`: the operator pays out of a small
budget for a verdict that measured nothing, and reads a rejection of a candidate
that was never scored. If it landed outside that group the run proceeds and the
drift is invisible. `exclude` drops only a testcase whose skip stands alone: one
that also carries a failure or an error demonstrated something and scores false
under either policy.

`--kind rule` goes further and refuses. A scenario whose mechanism errored,
whose scores are missing, or whose judge reported a failure is a config error
that exits 2 and names the scenarios, rather than scoring them false. The two
policies answer the same threat and differ on what a wasted consultation is
worth. Scoring a failed judge as a real failure is a measurement of the judge,
not of the rule, and the gate would spend one of a small budget of held-out
consultations to reach a verdict that carries no information about the
candidate. The rule path is also the one that can least afford the noise: it is
single-shot against an LLM judge, and scoring identical rule text twice moved 5
of 24 tasks across the pass threshold (ADR-087 Open Requirement 6, #3445),
while the agent path averages over runs. Exit 2 is the loop's documented signal
to stop and let an operator re-run the scorer.

Calling `rule_results` from `_optimizer_adapters` directly still fails closed.
The refusal lives in `extract`, so the library keeps one contract and the
command that spends budget keeps a stricter one.

### Reading a rule across several runs

Refusing a broken judge does not help when the judge answers cleanly and
differently each time. `--kind rule` takes more than one `--input`, one report
per run of `eval-rule-activation.py`, and reduces each scenario across them
before the bar is applied:

```bash
uv run --frozen python "$OA" extract --kind rule \
    --input run1.json run2.json run3.json --reduce mean > base.json
```

The reduction is over scores, not over verdicts. Thresholding each run and then
voting would throw away the distance from the bar, which is the only thing that
says whether a disagreement was close. Reducing first matches what
`agent_results` already does: collapse the runs to one number, apply the bar
once.

`--reduce` takes `mean` (the default), `min`, `max`, or `median`. `min` reads as
"every run must clear the bar" and `max` as "any run may", so the strict and
lenient readings are both reachable without a second flag. `--kind agent` and
`--kind hook` still take exactly one `--input` and refuse a second, because
`agent_results` already averages over runs and `pytest_results` is
deterministic.

One run behaves exactly as before, so an existing caller needs no change:
`rule_results_multi([scenarios])` and `rule_results(scenarios)` agree.

The runs must agree on which scenarios they scored, and a scenario with
evidence in some runs but not others is refused rather than reduced over
whatever is left. Both are the fail-closed policy above, applied to the shape
this flag introduces. Scoring a partially evidenced scenario false would let a
judge error on the incumbent's run read as a failing scenario, so a candidate
that merely ran cleanly would look like a fail-to-pass improvement. That is the
spurious accept the gate exists to prevent, arriving through the scorer.

### Two kinds of judge noise, two reducers

`--reduce` is not the only reduction on this path, and the two do not see the
same noise.

`eval-rule-activation.py` can score a scenario more than once inside a single
run. `--judge-repeats` sets how many, the report persists every answer under
`score_samples`, and `--rule-reduce` collapses them per score key before
anything else looks at the run. That drops one erratic judge call.

`--reduce` then collapses whole runs, one report file each, after the samples
inside each are already collapsed. That catches a different failure: a whole
report landing on the far side of the bar. The ADR-087 measurement found 13 of
24 tasks moving between runs and 5 crossing the accept threshold, mean absolute
movement 0.49 on a five-point scale, which is movement no amount of
within-run repetition can average away.

```bash
uv run --frozen python "$OA" extract --kind rule \
    --input run1.json run2.json run3.json \
    --rule-reduce median --reduce mean > base.json
```

Both take `mean`, `min`, `max`, or `median`. `--rule-reduce` defaults to
`median`, which is the resistant choice for a handful of samples where one
outlier is the thing being removed. `--reduce` defaults to `mean`. A report
carrying no `score_samples` is unaffected by `--rule-reduce`, so reports
written before this existed read the same.

Order matters and is fixed: samples collapse inside a run, then runs collapse
across reports. Reducing runs first would mix a scenario's outlier sample into
the cross-run number and hide the movement `--reduce` exists to see.

How many runs is a judgment, not a setting. The benchmark behind this flag
(ADR-087 Open Requirement 6, #3445) measured a mean absolute movement of 0.49
points on the five-point scale between two scorings of identical rule text.
Three runs at `mean` is the cheapest configuration that can outvote one outlier.
Nothing here enforces a count, and one run remains legal so the flag can be
adopted without rescoring everything first.

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
    --out split.json | uv run --frozen python -c "import json,sys;print(json.load(sys.stdin)['fingerprint'])")

# Per step: check the budget, reject a repeat, apply, rescore, gate.
uv run --frozen python "$OA" budget --step 3 --total 12

# Exit 1 means this edit was already rejected, so skip it. Exit 2 means the
# command itself failed and the loop must stop rather than treat a typo in a
# path as a clean finish.
uv run --frozen python "$OA" buffer-check --buffer rejected.json --patches p.json \
    --artifact target.md
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

On reject, revert the file and run `buffer-add` with the artifact path so the
same edit is not re-proposed against the same artifact state. On accept, the
candidate becomes the incumbent and prior rejections against the old artifact
state expire.

`buffer-add --reason` is required and takes free text. It records why the edit
was rejected so a later step, or a reader auditing the buffer, can tell a gate
reject apart from a refused patch or an operator veto. Name the deciding
signal, not the intent: `gate: sel score dropped 0.62 -> 0.55` tells the next
reader something, `bad edit` does not.

### Reporting the test group, once

When the loop has converged and the consultation budget is spent, one command
reads the third group:

```bash
uv run --frozen python "$OA" report --results cand.json --split split.json
```

It prints `score`, `group`, `n`, `corpus_verified`, and `fingerprint`, and no
`decision` field, because it reports rather than decides. Exit 0 on a number,
1 on a refusal, 2 on a split it cannot use.

Five things bound it. It has no `--group`, so it reads `test` and nothing
else. It answers once per test group: the second call refuses, and the record
is keyed on the group's membership, so copying or renaming the split does not
buy another. Its budget is separate from the gate's, so an exhausted
consultation budget does not block the report and a spent report does not
block the gate. It honours the corpus pin the gate honours, refusing results
that name a corpus the split does not, which the gate refuses because a
comparison across a corpus change measures the change too, and this command
refuses because nothing downstream compares the number at all. And a results
file that does not cover the test group is refused **after** the read is
charged, for the same reason the gate charges first: a free coverage probe
against a withheld group is an oracle over its membership.

The corpus refusal is free, unlike the coverage one. A corpus identity is a
header on the file the caller supplied, decidable without touching the group,
so it is read before the lock and charges nothing. `corpus_verified` reports
whether the check ran at all: the rule and hook paths publish no corpus
identity, so `false` there means unchecked rather than failed.

Score the artifact over the whole task set before calling this. There is one
attempt, and spending it on a short results file means re-splitting and
re-running the loop.

`--test-ratio` defaults to 0, so this command has nothing to read unless the
split was drawn with a test group. It says so rather than reporting a score
over an empty set.

### What the gate refuses

A strictly-greater held-out score is the only way to earn an accept. A tie is a
reject, because an edit that did not move the held-out score is churn and churn
on an artifact costs review attention forever.

The gate reads `sel` and only `sel`. There is no flag to point it at another
group, because a gate that can be aimed at the group the author has been
reading is not a gate.

`score` refuses too, on the one condition it shares with the gate. Both read
the split file, and both redraw it from its own recorded seed, task set, and
ratios to check that the recorded groups are what those inputs produce. A file
that fails redraw was hand-edited or corrupted after `split` wrote it, and
`score` will not put a number on it.

The reason is what `score` prints beside the number. It echoes the split's
fingerprint so the loop can pass it to `gate --incumbent-fingerprint` without
opening the file, and on an edited split that fingerprint no longer names the
groups just scored: two runs of `score` return one fingerprint and different
numbers, which is exactly the confusion the fingerprint exists to prevent.
Nothing unsound reaches a verdict either way, because `gate` runs the same
check and rejects. What the refusal buys is where the operator finds out. The
gate is the end of a step that has already paid for a candidate, so a check
that only fires there charges for the discovery.

The two commands report it differently on purpose. `gate` emits
`decision: REJECT` because its caller is a loop that branches on the document.
`score` raises a `ConfigError` and exits 2, the same way it reports a split
whose keys are missing, because a hand-edited split is a malformed one and
`score` has no decision vocabulary to refuse in.

### What the seam does and does not protect

Read this before citing a run of this loop as evidence.

**What it is.** A consultation-budgeted comparison over a public benchmark,
relying on a cooperating optimizer not to inspect task definitions and result
files it can already reach. **It is not held-out validation of unseen tasks.**

Three things make that the honest description rather than an overcautious one:

- **`extract` can emit either the full result set or one split group.** Its
  output is an envelope that records the scoring parameters beside the
  `{task_id: bool}` mapping. When `--split` and `--group` are supplied, it first
  requires coverage of the whole split universe, then emits only that group.
  The gate refuses mismatched extraction parameters and refuses any results
  file that does not cover `opt`, `sel`, and `test`.
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
- A recorded charge survives a crash on POSIX. The ledger is written to a temp
  file, fsynced, renamed, and the *parent directory* is then fsynced too.
  Without that last step the bytes were durable but the directory entry
  pointing at them was not, so a host losing power after a reported charge
  could come back with the rename undone and hand the consultation back for
  free. That is the one outcome charging before scoring exists to prevent, so
  a charge a crash can erase defeats the ordering it was written to protect.
  Windows cannot open a directory as a descriptor, so the step is skipped on
  that platform rather than failed, and the skip is a real gap. `os.replace`
  is atomic on Windows, but atomicity is not the property at stake here:
  CPython calls `MoveFileExW` with `MOVEFILE_REPLACE_EXISTING` alone, omitting
  `MOVEFILE_WRITE_THROUGH`, the flag Microsoft documents as waiting for the
  move to reach disk. So a Windows host can lose a recorded charge to a power
  cut the same way an unsynced POSIX host can. The skip is silent rather than
  warned because it holds for every write, and a warning on each one would
  cost stderr its signal. A directory that opens and then refuses to sync is
  warned about on stderr and not raised: the write and the rename have already
  succeeded by then, and in the ledger's case the consultation has already
  been charged, so aborting would spend a look and return no verdict. That is
  the same trade the charging order exists to avoid, pointing the other way.
  Every other failure in that function precedes the rename and leaves the
  destination untouched, so those still refuse. That warning goes through the
  same redaction the raised errors do, and cannot itself fail: a diagnostic
  printed after a success must not become a new way to lose the work it is
  reporting on, and must not disclose in plain text what the exception path is
  required to redact. "Cannot fail" is enforced as a rule rather than as a
  list of the failures anyone has demonstrated: an earlier version suppressed
  `OSError` because that is what a reviewer's closed-stream demonstration
  raised, and a stream closed for real raises `ValueError`. There is a third
  rule alongside those two. The warning must not land on the stream carrying
  the verdict. `sys.stderr` can be absent in an embedded or windowed
  interpreter, and printing to a file of `None` does not skip the write, it
  falls back to stdout, where the JSON a caller parses is. A diagnostic that
  corrupts the payload it is diagnosing is worse than one that crashes,
  because nothing reports it. "Absent" covers two cases and for four rounds
  the code handled one. A harness can blank the attribute or delete it, and
  the second turns reading it into an `AttributeError` raised before the
  suppression is even entered, from the line whose only job is to decide
  whether to warn. Reading it with `getattr` routes that case into the `None`
  branch already there, which enforces the no-abort rule at the last
  expression standing outside the guard without adding a second branch to it.
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

  Held-out outcomes still do not stay behind that line by themselves. `extract`
  is group-aware, but a caller can still run the ungrouped form unless a
  controller owns the scorer output and hands the optimizer only `opt`. What
  the budget bounds is how many times an edit may be compared against the
  held-out group through the gate, which is the loop's own **gate comparisons**
  against that group. It is not a bound on total selection pressure. Closing
  that needs the trusted controller in ADR-087 Open Requirement 1.

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
one. A budget of five consultations each judged at 0.05 does not deliver 0.05.
Bounding the family without assuming anything about dependence gives
`5 * 0.05 = 0.25` by the union bound; the exact `1 - 0.95**5`, about 0.226,
holds only if the five comparisons are independent, and five looks at one
selection group are not. Either way it is roughly five times the number an
operator asking for 0.05 believes they are getting. So the gate spends the bar
across the declared budget by Bonferroni: each comparison is held to
`--max-p / --max-consultations`. Bonferroni is used rather than a sharper
independence-dependent correction precisely because it controls the family bar
under arbitrary dependence between the comparisons. The verdict reports both as
`max_p` and `max_p_per_comparison`. That control is conditional, and the
condition is worth naming: Bonferroni tolerates any dependence between the
comparisons, but it still assumes each per-comparison p-value is valid on its
own. The exact McNemar tail earns that only if the discordant pairs behave as
independent fair coin flips under the null, and correlated scorer noise breaks
it. That is not hypothetical here. The rule-path null control described above
restored the artifact byte for byte and reproduced both gains, which is direct
evidence that outcomes on this harness move together. Read the family bar as
holding under any dependence between the comparisons **given** per-comparison
validity, and treat the second half as something this harness does not
guarantee. Two further consequences worth stating plainly. Raising the
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

Two accounting keys appear in those documents and answer different questions.
`consultations` is what **this run** charged: zero on every refusal that
declines before charging, one on the paths that charged and went on to score.
It is present at every emit site, so the key answering "what did this cost me"
is never missing exactly where the answer is nonzero. `sel_consultations` is
the **running total** for the selection group, the charge included, and appears
only where that total is both known and this group's. On a ledger key mismatch
the recorded count belongs to a different group, so it is withheld rather than
reported as a zero that was never true; absence is the honest answer when the
number on disk is not yours to quote.

`group` and `fingerprint` follow the same shape for the same reason. Both name
the held-out group whose ledger this run opened, so they appear on the
documents the gate emits once it holds that lock, and are absent from the
refusals decided before it takes one: a drifted split, and the corpus
preflight. The corpus refusal is the single exception, and it is deliberate.
It is one document emitted from both sides of the lock, so it carries only
what the earlier side can say, which is what keeps the key set from answering
which of the two reads caught the disagreement.

Filling those keys into every refusal looks like a schema cleanup and is not.
On a drifted split the recorded fingerprint is the value the drift check has
just disproved, so a payload carrying both would report a fingerprint beside a
reason saying that fingerprint does not describe the file. The rule across all
four keys is one rule: a verdict carries the facts the site emitting it can
state honestly, and an absent key is the honest answer, not a gap.

That promise has been broken three times by exceptions that reached the top
level under a class the handler did not name, and each cost a traceback where a
caller was parsing stdout. `_write_atomic` created its temp file before the
block that
turns a write failure into a `ConfigError`, so `split --out` into a directory
that does not exist raised `FileNotFoundError` uncaught. `_read_json` did not
name `UnicodeDecodeError`, which subclasses `ValueError` rather than `OSError`,
so a binary input was reported under the decoder's own class while `_read_text`
reported the same bytes as a config problem. The third was the cleanup itself:
`_write_atomic` unlinked its temp file inside the handler without guarding the
unlink, so a parent whose permissions were revoked after `mkstemp` failed both
calls and the caller got a traceback naming the cleanup instead of a document
naming the write. Cleanup cannot stand in for the failure it cleans up after,
so the unlink is now suppressed on `OSError` while every other class still
escapes. All three now answer exit 2 with a `ConfigError` document.

The fourth was worse than a traceback, because it answered. `_emit` writes with
a bare `print`, so a reader that closed early made it raise `BrokenPipeError`,
an `OSError`, which the handler did not name. It left `main` and exited 1, and
exit 1 on this CLI is REJECT: a verdict on a comparison that never finished. On
`gate` the ledger write precedes the final emit, so a consultation had already
been charged against a fixed budget and the answer it bought was discarded.
CPython contributed a second mode on its own. When the payload fits the pipe
buffer the write succeeds and the shutdown flush fails instead, which prints
`Exception ignored while flushing sys.stdout` and replaces the status with 120,
so the caller saw neither a verdict nor a config failure. Measured on this
branch: `split` over 20000 tasks into a closed reader exited 1 with a traceback,
and `budget` into the same exited 120. Both now exit 2 with one line on stderr.
`main` is a thin `except OSError` guard over `_dispatch`, which holds the old
body, and the guard covers parser construction too, because `print_help` writes
to stderr and stderr closes for the same reasons stdout does. The handler does
not retry the write on the stream that just failed; the exit code carries it.

Catching `OSError` that broadly at the top gives up nothing. Any `OSError` that
reached `main` before was an unhandled crash exiting 1, and exit 2 is the
correct answer for a run that produced no decision.

| Code | Meaning |
|------|---------|
| 0 | Accept, novel patch, or plain success |
| 1 | Reject, already-rejected patch, or a refused patch |
| 2 | Bad arguments, unreadable input, malformed data, or a stream that could not be written |

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
only the 14 optimize ids were read. The chosen edit went to the then-existing
working-with-legacy-code rule file, whose two visible failures both
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

### A retracted agent-path claim, and the guard it produced

An earlier revision of this section claimed the architect spike reproduced the
rule finding: two runs of the same model against the same eight fixtures, five
of eight moving, and a null control that earned an ACCEPT. **That claim was
wrong and is withdrawn.** The two runs did not use the same fixtures.

Every agent report carries `fixture_set_sha`, and the schema comment says what
it is for: it "allows the report consumer to verify that two runs hit the same
set." The two architect runs report `be99fa1b1180` and `26136df314d6`. All eight
individual `fixture_sha` values differ as well. The fixtures were committed once,
on 2026-05-29, after both runs, and the committed copies match the later run, so
the earlier run's corpus is not recoverable. The pair cannot support a null
control because the corpus is a second changed variable.

The two supporting pairs fail the same test for a different reason. The critic
and high-level-advisor comparisons hold `fixture_set_sha` constant but differ in
`agent_prompt_sha`, so the prompt is the changed variable. The "twelve of
twenty-four" figure pooled three confounded comparisons and is withdrawn in full.

There is no agent-path null control in this repository. The honest state of the
evidence is one path measured, not three:

- **Rule path, measured.** The artifact was restored byte-for-byte and verified
  identical to `origin/main` before the re-run, so the corpus and the artifact
  were both held fixed. That control stands, and it is the one that matters:
  both held-out gains that earned the ACCEPT reproduced under the no-op.
- **Agent path, unmeasured.** Running it requires two runs that agree on
  `fixture_set_sha` and on `agent_prompt_sha`. No committed pair does.
- **Hook path, deterministic by construction.** `pytest_results` re-runs to the
  same mapping.

The error was worth more than the claim would have been. The report schema
already carried the field that falsifies it, the comparison tool never read that
field, and nothing in the loop would have stopped anyone else from making the
same mistake. `gate` now refuses a comparison whose two sides disagree about the
corpus. See "Refusing an incomparable pair" below.

### What this means for running the loop

> **A `gate` ACCEPT is only as trustworthy as the benchmark under it.** `gate`
> without `--max-p` guards against an optimizing agent gaming its own benchmark.
> It does not guard against the benchmark being noisy. Those are different
> threats and only the first is closed by default. On the one path where a
> control was run, the default issued an ACCEPT for gains a no-op reproduced.

Practical consequences, until repeated sampling lands:

- Against `rule_results` or `agent_results`, run a null control alongside any
  accept before citing it, and pass `--max-p`. Restore the artifact
  byte-for-byte, re-run the identical scorer, gate the result. If the no-op
  earns an accept, or gains the same tasks the real edit gained, the loop is
  measuring its own variance.
- Hold the corpus fixed and prove it, do not assume it. Two runs of the same
  agent are not comparable unless they agree on `fixture_set_sha`. `gate` now
  checks this for you and refuses when they disagree, because the one time this
  was done by eye it was done wrong.
- If the tasks that moved are not the tasks your edit touched, that is the
  cheap early signal. The rule finding showed it before the control was run.
- Against `pytest_results` neither applies. That path is deterministic, so a
  repeated run of the same suite against the same tree gives the same mapping,
  and an accept there means what it says.

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

### Refusing an incomparable pair

`split` records the corpus of the results it was drawn from, and `gate` refuses
when the split's pin and the two results files name more than one corpus
between them. A results file that names no corpus says so, as `"corpus": null`,
and that counts as a value like any other, so a known corpus beside a null one
is a disagreement. A split with no `corpus` key at all names nothing and is
dropped before counting, which is why a pinless split beside two files agreeing
on one corpus is not refused. Null everywhere is one value rather than two, so
it is reported as `corpus_verified: false` instead of refused, which is what
keeps the gate usable on the rule and hook paths that publish no corpus
identity:

```text
decision: REJECT   compared: false   consultations: 0
reason: the split and the two results files do not agree on one corpus, so a
        comparison between them measures the corpus change as well as the edit.
```

That output is a replay, not an illustration. Extracting the two tracked
architect reports, `20260528T051601Z-70c6ae97` and `20260528T055934Z-5f4d8ad4`,
and gating them exactly as the false accept was produced now returns the refusal
above, exit 1, with no ledger file written.

Seven properties, each chosen against a specific failure:

- **It costs nothing.** The decision comes from three header fields, so it lands
  beside the split-drift refusal and ahead of the ledger. A mismatched pair is
  unusable at any budget, so charging for it would sell the caller a
  consultation it can never spend.
- **An exhausted budget does not mask it.** Same precedent as the `--max-p`
  range check. A refusal decidable without the held-out group must not be
  reordered behind one that needs the ledger, or the operator is told to buy
  budget for a comparison that can never be valid. The converse also holds: the
  preflight reads headers only and answers "unknown" to every content problem,
  so a malformed verdict mapping can never answer in place of the ledger. The
  full read happens after the guards, where it reports properly.
- **Stripping a results envelope does not delete it.** The first cut compared
  the two files against each other and refused only when both declared a corpus
  and the two disagreed. That made the refusal reachable by omission: piping
  either side through anything that emits a bare mapping, which is what every
  consumer wrote before the envelope existed, turned "known to differ" into
  "unknown", and unknown compared. Two changes close it. The split pins the
  corpus, so the value lives in the baseline commitment rather than being
  inferred from the pair. And one known corpus beside an unknown one is a
  conflict, because a pair scored on one corpus does not have one side that
  forgot.
- **Deleting the split's pin is reported, not refused.** Removing the `corpus`
  key leaves two agreeing results files and nothing to contradict them, so the
  conflict rule has no disagreement to find. Refusing that shape would also
  refuse every `--tasks` split and both artifact classes that pin nothing at
  all. The verdict carries `corpus_pinned` instead: `true` means the split named
  the corpus both results carry, `false` means only the two results were checked
  against each other. A sixteenth review found the earlier wording claiming this
  case was refused when it was not.
- **What was scored is what was checked.** The preflight reads file headers; the
  comparison is scored from a second, full read. Only the second is
  authoritative, so the conflict rule runs again against the loaded values
  before a consultation is charged. Without that, the two reads never had to
  agree and the gap between them was a window a file could change in.
- **Both checks speak with one voice.** The two refusals are the same document.
  The gate's copy briefly added the ledger's prior spend, so the key set alone
  told the caller which of the two reads caught the mismatch, which is the
  property the shared builder exists to prevent. It was also the wrong number
  to report: the budget guard runs before the recheck, so budget is never
  exhausted by the time it fires, and prior spend cannot change what the caller
  does next. Both report `consultations: 0`, the one claim each can make
  honestly, which is that this run charged nothing.
- **It leaks nothing.** The reason names neither task ids nor the holdout key,
  so a caller cannot use repeated mismatches to probe the held-out group. The
  preflight runs under the same digest scrubber as the ledger paths.
- **Unknown everywhere is reported, not refused.** Only the agent path publishes
  a corpus identity. Refusing unknown on all three would disable the gate for
  rules and hooks to guard a case it cannot detect there anyway, so the verdict
  carries `corpus_verified` instead. `false` means the check never ran. A real
  mismatch never reaches a verdict at all.

A corpus identity has to look like one: 64 lowercase hex characters, the form
`hexdigest()` emits. An unchecked string reports success on values that identify
nothing, and two reports both carrying `fixture_set_sha: ""` compared as
verified until a fifteenth review pointed at it.

Task ids are not a substitute for this check, which is the whole reason it
exists. All eight fixture ids matched across the two architect runs while every
one of the eight fixture files differed. Identity of the keys says nothing about
identity of what the keys point at.

**The limit, stated plainly.** The split file is caller-supplied and its corpus
pin is outside the fingerprint, so a caller who edits the split can still get an
incomparable pair through: delete the pin, and two results files scored on one
corpus compare against a split drawn from another. The verdict reports
`corpus_pinned: false` when that happens, but nothing refuses it. Closing it
needs authenticated provenance, which this does not have. What it defends against is
omission: a field going unread, an envelope getting stripped, a pair being
eyeballed instead of checked. That is the failure that actually happened.

The remaining gap is that two of the three paths have no corpus source to read.
That is ADR-087 open requirement 12: an identity derived from task contents,
which needs a seam that carries them.

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

Set `EVAL_PROVIDER` to use a non-Anthropic transport (e.g., `openai`, `github-models`). When a
keyless provider is selected, `ANTHROPIC_API_KEY` is not required.

## Token Budget Measurement

The Copilot CLI session counter is NOT a reliable tool for measuring instruction corpus size.
Its reported token count folds in MCP tool definitions and cache accounting alongside
instruction text. The number is non-monotonic: adding instruction files can cause the counter
to decrease (issue #3906).

Use `scripts/validation/instruction_budget.py` for before/after instruction corpus measurement.
It reads instruction files directly, applies `applyTo` glob matching for a given file type, and
reports a deterministic sum:

```bash
# Report instruction tokens for .py files
uv run --frozen python scripts/validation/instruction_budget.py --file-type .py

# Report instruction tokens for .md files
uv run --frozen python scripts/validation/instruction_budget.py --file-type .md
```

This output is stable across sessions, does not depend on MCP state or CLI caching, and is
the correct input for optimization decisions.

## References

- [ADR-057](.agents/architecture/ADR-057-prompt-behavioral-evaluation.md)
- [ADR-023](.agents/architecture/ADR-023-quality-gate-prompt-testing.md)
- [Methodology](.agents/testing/prompt-eval-methodology.md)
