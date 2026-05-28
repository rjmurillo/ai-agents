# Analyst Eval Spike

Agent-vs-baseline eval for the `analyst` agent. Two runs landed in this PR: synthetic-corpus run (20260528T040743Z-643d1793; analyst -0.083) and real-issue corpus run (20260528T043356Z-ee538fef; analyst +0.125).

## Question

Does the analyst's specialized system prompt (evidence-level tagging, search-
before-claiming, hypothesis ranking, open-questions discipline) outperform a
naive baseline on a held-out investigation corpus?

## Method

Driven by [scripts/eval/eval-agent-vs-baseline.py](../../scripts/eval/eval-agent-vs-baseline.py).
Per fixture: N runs * 2 variants (baseline = "Review the following input." vs
treatment = `templates/agents/analyst.shared.md`). Verdict vocabulary is fixed
by the runner contract: `IDENTIFY | OK | ESCALATE`.

## Layout

```text
evals/analyst-spike/
  fixtures/          F001.json .. F018.json + README.md (provenance, distribution, rationale)
  runs/<RUN_ID>/     runs.jsonl per live run
  reports/<RUN_ID>/  REPORT.md + report.json per live run
```

## Reproducibility

```bash
# Dry-run (no API calls)
python3 scripts/eval/eval-agent-vs-baseline.py \
    --agent analyst \
    --fixtures evals/analyst-spike/fixtures \
    --dry-run

# Live (default 3 runs/variant; 18 * 3 * 2 = 108 calls)
python3 scripts/eval/eval-agent-vs-baseline.py \
    --agent analyst \
    --fixtures evals/analyst-spike/fixtures
```

## Cross-references

- [evals/security-spike/README.md](../security-spike/README.md) - reference spike.
- [evals/skill-triage.md](../skill-triage.md), [evals/agent-triage.md](../agent-triage.md) - classification matrices.
- [evals/baseline-report.md](../baseline-report.md) - aggregate baseline across all spikes (once landed).
