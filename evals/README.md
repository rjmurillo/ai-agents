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

A fixture in `evals/security-spike/fixtures/` MUST NOT duplicate a scenario in `tests/evals/security-scenarios.json` verbatim. Where prior public material is reused, it is paraphrased substantially and tagged `provenance: paraphrased-from-public` (REQ-004 AC-4).

## Layout

```
evals/
  security-spike/
    fixtures/        # F001.json .. F010.json + README.md
    runs/<RUN_ID>/   # runs.jsonl per live run (T4-5)
    reports/<RUN_ID>/  # REPORT.md + report.json per live run (T4-5/T4-7)
```

`<RUN_ID>` is `<ISO8601-compact>-<uuid4>` per DESIGN-004 §Persistence Layout.

## Cross-references

- Plan: `.agents/plans/active/PLAN-1854-agent-eval-harness-spike.md`
- Spec: `.agents/specs/requirements/REQ-004-agent-eval-harness-spike.md`
- Design: `.agents/specs/design/DESIGN-004-agent-eval-harness-spike.md`
- Task: `.agents/specs/tasks/TASK-004-agent-eval-harness-spike.md`
- ADR-057: `.agents/architecture/ADR-057-prompt-behavioral-evaluation.md`
