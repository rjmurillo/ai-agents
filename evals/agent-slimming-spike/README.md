# Agent-slimming eval results

Legacy experiment results for the April 2026 agent prompt-slimming work.
These files are committed eval outputs, not planning artifacts.

## Question

Did slimming the targeted agent prompts preserve role behavior while reducing
prompt size, and did reference enrichment improve skill answers enough to pass
the kill gate?

## Provenance

The files were first committed under `.agents/planning/` before `evals/` became
the repository system of record for eval inputs and outputs. Issue #3435
re-homed them here without changing JSON bytes.

| Bundle | Files | Origin | Notes |
|---|---:|---|---|
| `reports/20260411T000000Z-9685367b/` | 5 | Commit `9685367b2`, PR #1614 | Skill reference kill-gate and extended prompt eval outputs. |
| `reports/20260412T000000Z-4aa87f2f/` | 28 | Commit `4aa87f2fe`, PR #1617 | Agent baseline, post-review, slim, verify, and spot-check outputs. |

The run ids use the eval directory's compact timestamp plus eight-hex suffix
shape. The suffix is the source commit prefix because these are legacy outputs
with no recorded runner UUID.

## Layout

```text
evals/agent-slimming-spike/
  reports/20260411T000000Z-9685367b/
  reports/20260412T000000Z-4aa87f2f/
```

## 2026-04-11 files

- `eval-decision-critic.json`
- `eval-extended-prompts.json`
- `quality-results-api.json`
- `quality-results-extended.json`
- `quality-results-full.json`

## 2026-04-12 files

- `agent-baseline-analyst.json`
- `agent-baseline-results.json`
- `agent-baseline-v2-results.json`
- `agent-post-review-results.json`
- `analyst-slim-results.json`
- `context-retrieval-slim-results.json`
- `critic-slim-results.json`
- `critic-slim-v2-results.json`
- `explainer-slim-results.json`
- `explainer-slim-v2-results.json`
- `explainer-slim-v3-results.json`
- `implementer-slim-results.json`
- `implementer-v2-results.json`
- `implementer-verify.json`
- `issue-feature-review-slim-results.json`
- `issue-feature-review-verify.json`
- `milestone-planner-slim-results.json`
- `milestone-planner-verify.json`
- `orchestrator-slim-results.json`
- `roadmap-slim-results.json`
- `skillbook-slim-results.json`
- `skillbook-slim-v2-results.json`
- `skillbook-verify-results.json`
- `spec-generator-slim-results.json`
- `spot-check-devops.json`
- `spot-check-memory.json`
- `spot-check-quality-auditor.json`
- `spot-check-task-decomposer.json`

## Historical source paths

All 33 JSON files moved from `.agents/archive/planning/`. Their immediate
pre-move paths were produced by the #3431 archive pass, which moved the older
`.agents/planning/` contents into `.agents/archive/planning/` without changing
filenames.

## Related records

- Issue: #3435
- Archive pass: #3431
- Agent-slimming spec: `.agents/archive/planning/SPEC-agent-consolidation.md`
- Knowledge reference report: `.agents/archive/planning/quality-results.md`
