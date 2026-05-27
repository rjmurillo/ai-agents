# requirements-interview Eval Spike

Held-out agent-vs-baseline corpus driving `scripts/eval/eval-agent-vs-baseline.py` against the `requirements-interview` skill.

## Skill under test

`.claude/skills/requirements-interview/SKILL.md`

> Adversarial requirements interview that walks the design tree to elicit testable requirements before any code is written. Implements the grill-me pattern - ask relentlessly, recommend an answer for every question, and resolve dependencies between decisions one branch at a time. Skip any question the codebase can already answer.

## Why eval-worthy

Adversarial requirements elicitation. Question coverage is judgment.

See `evals/skill-triage.md` for the classification rationale and the full per-skill matrix.

## Status

Scaffold only. Fixtures, runs, and reports are owned by the operator who lands the first live run for this skill.

## Layout

```text
evals/requirements-interview-spike/
  fixtures/           # F001.json .. FNNN.json + README.md (TBA)
  runs/<RUN_ID>/      # runs.jsonl (per-trial outcomes; created on first live run)
  reports/<RUN_ID>/   # REPORT.md + report.json (created on first live run)
```

`<RUN_ID>` is `<ISO8601-compact>Z-<uuid4-hex8>` per DESIGN-004. The runner builds it; operators MAY substitute with `--run-id <value>` provided the shape matches.

## How to author the first fixture

1. Read the skill's SKILL.md and identify the bounded judgment it produces (verdict, finding, score, recommendation, design).
2. Choose 3 verdict bands minimum (e.g., `IDENTIFY`/`OK`/`ESCALATE`, `KEEP`/`PRUNE`/`INVESTIGATE`, `A`/`B`/`C`/`D`/`F`).
3. Write 6-10 fixtures spanning every band. At least 30% should be **agent-discriminating**: cases where the naive baseline ("here is the input; respond with one of `<bands>`") cannot answer correctly without knowledge encoded in the skill.
4. Each fixture: `schemaVersion`, `id`, `policy_id`, `input`, `provenance` (`synthetic` | `paraphrased-from-public`), `assertions[]` (each `{kind, expected_value | pattern}`), `tags`. Mirror `evals/security-spike/fixtures/F001.json` for the canonical shape.
5. Update `fixtures/README.md` with the per-fixture provenance table and verdict distribution. Mirror the shape used in `evals/security-spike/fixtures/README.md`.

## Cross-references

- `evals/README.md`. Eval directory scope.
- `evals/skill-triage.md`. Classification matrix.
- `evals/security-spike/`. Reference implementation.
- `scripts/eval/eval-agent-vs-baseline.py`. Runner.
- [ADR-057](.agents/architecture/ADR-057-prompt-behavioral-evaluation.md). Prompt behavioral evaluation.
