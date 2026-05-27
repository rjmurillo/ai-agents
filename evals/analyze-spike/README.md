# analyze Eval Spike

Held-out agent-vs-baseline corpus driving `scripts/eval/eval-agent-vs-baseline.py` against the `analyze` skill.

## Skill under test

`.claude/skills/analyze/SKILL.md`

> Systematic multi-step codebase analysis producing prioritized findings with file-line evidence. Covers architecture reviews, security assessments, and code quality evaluations through guided exploration, investigation planning, and synthesis.

## Why eval-worthy

Multi-step codebase analysis producing prioritized findings. Pure judgment skill.

See `evals/skill-triage.md` for the classification rationale and the full per-skill matrix.

## Status

Scaffold only. Fixtures, runs, and reports are owned by the operator who lands the first live run for this skill.

## Layout

```text
evals/analyze-spike/
  fixtures/           # F001.json .. FNNN.json + README.md (TBA)
  runs/<RUN_ID>/      # runs.jsonl (per-trial outcomes; created on first live run)
  reports/<RUN_ID>/   # REPORT.md + report.json (created on first live run)
```

`<RUN_ID>` is `<ISO8601-compact>Z-<uuid4-hex8>` per DESIGN-004. The runner builds it; operators MAY substitute with `--run-id <value>` provided the shape matches.

## How to author the first fixture

1. Read the skill's SKILL.md and identify the bounded judgment it produces (verdict, finding, score, recommendation, design).
2. Choose 3 verdict bands minimum (e.g., `IDENTIFY`/`OK`/`ESCALATE`, `KEEP`/`PRUNE`/`INVESTIGATE`, `A`/`B`/`C`/`D`/`F`).
3. Write 6-10 fixtures spanning every band. At least 30% should be **agent-discriminating**: cases where the naive baseline ("here is the input; respond with one of `<bands>`") cannot answer correctly without knowledge encoded in the skill.
4. Each fixture: `schemaVersion`, `id`, `provenance` (`synthetic` | `paraphrased-from-public`), `expected_verdict`, `verdict_options`, `rationale`, `tags`.
5. Update `fixtures/README.md` with the per-fixture provenance table and verdict distribution. Mirror the shape used in `evals/security-spike/fixtures/README.md`.

## Cross-references

- `evals/README.md`. Eval directory scope.
- `evals/skill-triage.md`. Classification matrix.
- `evals/security-spike/`. Reference implementation.
- `scripts/eval/eval-agent-vs-baseline.py`. Runner.
- ADR-057. Prompt behavioral evaluation.
