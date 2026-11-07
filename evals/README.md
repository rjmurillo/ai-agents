# evals/

Held-out evaluation corpora and run artifacts for agent-vs-baseline experiments.

## Scope

This directory holds **production-runnable** eval material:

- Fixture corpora used by `scripts/eval/eval-agent-vs-baseline.py`.
- Run records (`runs/<RUN_ID>/runs.jsonl`) and aggregated reports (`reports/<RUN_ID>/REPORT.md`, `report.json`) produced by live runs.
- README files documenting corpus design and provenance.

`evals/` is the **system of record** for the committed spike-eval inputs and outputs. The runner accepts any directory via `--fixtures <path>`; the convention is to point it at `evals/<agent>-spike/fixtures/` so committed fixtures, runs, and reports stay co-located. Pointing the runner elsewhere is operator-supported (for example, when iterating on a draft corpus before commit) but the resulting artifacts are not part of the system of record until they land under `evals/`.

## Relationship to `tests/evals/`

`tests/evals/` holds **scenario JSON for prompt-behavioral evaluation per ADR-057** (before/after prompt-change). Those scenarios drive `scripts/eval/eval-prompt-change.py` and are not held-out for the agent-vs-baseline spike.

ADR-057's prompt-change scenarios answer a different question than the agent-vs-baseline corpus: ADR-057 asks "did this prompt edit help or hurt?", while the agent-vs-baseline corpus asks "does this agent's specialization beat a generic baseline?".

| Directory | Purpose | Driven by |
|---|---|---|
| `tests/evals/*-scenarios.json` | Prompt-change before/after (ADR-057) | `scripts/eval/eval-prompt-change.py` |
| `evals/security-spike/fixtures/` | Held-out agent-vs-baseline corpus | `scripts/eval/eval-agent-vs-baseline.py` |
| `evals/adr-review-catch-rate/` | Seeded-defect corpus and results for the adr-review per-role catch rate (#5248) | `scripts/eval/eval_adr_review_catch_rate.py` |
| `evals/skill-bootstrap-capability/fixtures/` | Before/after capability tasks (gold at `acff1d0a1`, 2026-10-17) and results for skill-bootstrap | `scripts/eval/eval_skill_bootstrap_capability.py` |
| `evals/longitudinal-pilot/fixtures/` | Frozen five-task sequence, vendor-only vs vendor plus validated local context, with a stale-fact trap (#6993); live runs need an explicit `--ceiling-usd` | `scripts/eval/eval_longitudinal_pilot.py` |
| `evals/agent-slimming-spike/reports/` | Legacy agent-slimming experiment outputs from 2026-04 | `scripts/eval/eval-agents.py`, `scripts/eval/eval-knowledge-integration.py` |

A fixture in `evals/security-spike/fixtures/` MUST NOT duplicate a scenario in `tests/evals/security-scenarios.json` verbatim. Where prior public material is reused, it is paraphrased substantially and tagged `provenance: paraphrased-from-public` (REQ-004 AC-4).

## Skill evaluation: how this repo maps to the agentskills.io guide

The agentskills.io guide "Evaluating skill output quality" describes one loop:
run each case with and without the skill, grade with evidence, aggregate, find
weak assertions, iterate. The repo already runs that loop. These are the entry
points, so a new eval extends one of them instead of adding a format.

| Guide step | Where it lives here |
|---|---|
| Test cases (prompt, expected output) | `bootstrap_eval.py` cases file: `prompt`, `expected_output`, `grader`. A case without a `grader` is a draft; `bootstrap_eval.py check` validates it |
| With and without the skill | `bootstrap_eval.py` conditions `baseline` and `with_skill`; `scripts/eval/_claude_skill_harness.py` runs the CLI arm |
| Previous version as the baseline | `skillopt.py pair-gate` compares an incumbent bundle hash with a candidate; `eval_skill_bootstrap_capability.py` compares `before` and `after` checkouts |
| Timing and tokens per run | Optional `duration_ms` and `total_tokens` on each `bootstrap_eval.py` results row |
| Per-assertion evidence | `bootstrap_eval.py score --detail` prints `runs` with an evidence line each |
| `benchmark.json` mean, spread, delta | The `benchmark` block of `bootstrap_eval.py score` |
| Pattern analysis | Case `status` (`no_gap`, `flat`, `gain`, `regression`) plus `signals` (`never_passes`, `unstable_*`) |

Where this repo is stricter than the guide, it stays stricter:

- Graders are deterministic and frozen before any run. The guide adds
  assertions after the first output; here a draft case waits for an observed
  run, and `freeze` refuses it until it has a grader.
- A blind LLM judge is not a gate. ADR-058 Option 1 keeps an LLM judge as an
  advisory sidecar only.
- Held-out splits, exposed-task refusal, null controls, and the efficiency
  gate belong to `skillopt`. They have no counterpart in the guide.

Put per-skill cases under `evals/skill-cases/<skill>/cases.json`, not
inside the skill directory, because the skill tree is mirrored into every
platform package.

## Layout

```text
evals/
  security-spike/
    fixtures/        # F001.json .. F010.json + README.md
    runs/<RUN_ID>/   # runs.jsonl per live run (T4-5)
    reports/<RUN_ID>/  # REPORT.md + report.json per live run (T4-5/T4-7)
```

`<RUN_ID>` is `<ISO8601-compact>Z-<uuid4-hex8>` per DESIGN-004 §Persistence Layout. The runner builds it as `now().strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]` (e.g., `20260503T182553Z-eaa08f8d`); operators MAY substitute their own value via `--run-id <value>` provided it matches the same shape.

## Cross-references

- Plan: `.agents/archive/plans/PLAN-1854-agent-eval-harness-spike.md`
- Spec: `.project-toolkit/specs/requirements/REQ-004-agent-eval-harness-spike.md`
- Design: `.project-toolkit/specs/design/DESIGN-004-agent-eval-harness-spike.md`
- Task: `.project-toolkit/specs/tasks/TASK-004-agent-eval-harness-spike.md`
- ADR-057: `.project-toolkit/architecture/ADR-057-prompt-behavioral-evaluation.md`
