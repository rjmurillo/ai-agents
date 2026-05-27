# roadmap Agent Eval Spike

A/B eval spike for the `roadmap` agent. Default framing is **prompt-change control vs treatment** per the reviewer-asymmetry-spike template.

## Agent under test

`.claude/agents/roadmap.md`

> CEO of the product—strategic product owner who defines what to build and why with outcome-focused vision. Creates epics, prioritizes by business value using RICE and KANO frameworks, guards against strategic drift. Use when you need direction, outcomes over outputs, sequencing by

## Eval target

Outcome-focus, RICE/KANO application, strategic-drift detection.

See `evals/agent-triage.md` for the full per-agent matrix and other A/B framings (model swap, skill ablation, tool budget).

## Status

Scaffold only. Fixtures, runs, and reports are owned by the operator landing the first live A/B run.

## A/B design (default)

- **Control**: agent prompt at `origin/main`
- **Treatment**: agent prompt at HEAD
- **Trials**: 10 per fixture per condition (binomial)
- **Tests**: Fisher's exact (one-sided, treatment > control); Mann-Whitney U on `min_findings_count` when applicable
- **Acceptance**: p < 0.05 AND treatment mean > control mean, per-fixture AND aggregate

To swap framings (model swap, skill ablation, tool budget), update the runner invocation and document the swap in `fixtures/README.md`.

## Layout

```text
evals/roadmap-agent-spike/
  fixtures/          # F001.json .. FNNN.json + README.md (TBA)
  runs/<RUN_ID>/     # runs.jsonl (per-trial outcomes)
  reports/<RUN_ID>/  # REPORT.md + report.json
```

`<RUN_ID>` is `<ISO8601-compact>Z-<uuid4-hex8>` per DESIGN-004.

## Fixture authoring

1. Read `.claude/agents/roadmap.md` and identify the agent's bounded judgment output (verdict, finding, recommendation, design, plan).
2. Define 3-5 verdict bands in `verdict_options`.
3. Author 6-10 fixtures. At least 30% MUST be agent-discriminating per REQ-004 AC-5.
4. Per-fixture schema (matches reviewer-asymmetry-spike):

```json
{
  "schemaVersion": 1,
  "id": "F001",
  "agent": "roadmap",
  "input": "<scenario shown to the agent>",
  "provenance": "synthetic|public|paraphrased-from-public",
  "planted_issues": ["<one per planted finding>"],
  "scoring_rubric": {
    "kind": "<behavior under test>",
    "treatment_floor": "<what treatment must do>",
    "control_baseline": "<what control may do>"
  },
  "expected_verdict": "<one of verdict_options>",
  "verdict_options": ["<3-5 controlled labels>"],
  "min_findings_count": 3,
  "rationale": "<why this fixture distinguishes treatment>",
  "tags": []
}
```

5. Update `fixtures/README.md` per the reviewer-asymmetry-spike shape (provenance table, verdict distribution, per-fixture rationale).

## Reproducibility

```bash
# Dry-run (no API calls)
python3 scripts/eval/eval-reviewer-asymmetry.py --dry-run --agent roadmap

# Live A/B (10 trials per fixture per condition)
python3 scripts/eval/eval-reviewer-asymmetry.py \
    --agent roadmap \
    --trials 10 \
    --output evals/roadmap-agent-spike/runs/<run-id>.json
```

Note: `eval-reviewer-asymmetry.py` is the closest existing runner; it may need a small extension to take `--agent` as a parameter. If extending it costs more than authoring a per-spike runner, document the choice in the first fixture-authoring PR.

## Cross-references

- `evals/agent-triage.md`. Classification + A/B framing options.
- `evals/reviewer-asymmetry-spike/`. Template for multi-agent A/B (covers critic, qa, implementer).
- `evals/security-spike/`. Template for agent-vs-baseline (covers security).
- `scripts/eval/eval-reviewer-asymmetry.py`. A/B runner.
- ADR-057. Prompt behavioral evaluation.
