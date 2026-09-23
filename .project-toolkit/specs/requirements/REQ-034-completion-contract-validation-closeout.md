---
type: requirement
id: REQ-034
title: Close the completion-contract validation gaps
status: draft
priority: P1
category: functional
source: GH-5404
related:
  - DESIGN-032
  - TASK-043
created: 2026-09-23
updated: 2026-09-23
author: spec
tags:
  - eval
  - runtime-parity
  - completion-contract
---

# REQ-034: Close the completion-contract validation gaps

## Step 0 First Principles

### Q1 Demand Reality

rjmurillo, the repository owner, filed #5404 and set a session goal on
2026-09-23 to take it through ship and merge. PRs #5892 and #5898 each left
#5404 open with a named residual. ADR-105 records "No behavioral proof
against a live model" as the gap this work closes.

### Q2 Status Quo

The owner runs `eval_runtime_parity.py` by hand for the Claude harness only.
A Copilot run of an instruction fixture exits 2 because the evaluator calls
Copilot instruction loading unverified. Verdict scenarios 1 to 8 have no
recorded base versus candidate run. Pass or fail per scenario is judged by
eye across a few reports, with no stated threshold.

### Q3 Desperate Specificity

Issue #5404 itself. Its Validation criteria stay unchecked, so the issue
cannot close, and #5417 is blocked behind it.

### Q4 Narrowest Wedge

About 4 hours: verify the Copilot loading contract with a model-free probe,
add the Copilot instruction install path, fix the scenario 13 fixture
assertion, run the verdict ablation, and state a threshold.

### Q5 Observation

PR #5892 body: "A Copilot run with `instructions` exits 2 and names the
unverified loading contract." PR #5898 body: scenario 13 failed on the
`(?i)payment\.ts` regex while the semantic grader passed the reply. PR #5506
body: base/candidate ablation "not run".

### Q6 Future-fit

Yes. A second harness with a checked loading contract makes each new rule
fixture test both CLIs. The probe costs no model quota, so it scales with
fixture count.

## Step 0.5 Prior Art

Read: PRs #5506, #5892, #5896, #5898, the 2026-09-01 #5404 handoff, and
ADR-057's flakiness protocol in `scripts/eval/eval-prompt-change.py`. The
question is not already answered: Copilot loading was never probed because
the model quota was exhausted. New fact: `copilot instruction list --json`
lists sources with no model call.

## Problem Statement

Issue #5404's Validation criteria are still open. Copilot instruction
fixtures are refused, one fixture assertion rejects valid replies, the
verdict ablation has no evidence, and no pass threshold is written down.

## User Stories

- As the repository owner, I run one instruction fixture under Copilot CLI
  and see either a graded result or an exact exit code.
- As a rule author, I see which instruction files each CLI loaded, so a
  pass is not an artifact of leaked instructions.
- As a reviewer, I read one threshold that decides pass or fail per
  scenario.

## Ontology

- **Fixture**: one runtime-parity case with a prompt, assertions, and controls.
- **Instruction file**: a canonical rule under `.claude/rules/`.
- **Copilot projection**: the generated `.github/instructions/<name>.instructions.md`
  for one instruction file.
- **Instruction listing**: the JSON from `copilot instruction list --json`.
- **Scenario**: one of the 14 rows in the #5404 matrix.

## Data Model

A fixture keeps its `instructions` list of canonical paths. The Copilot
projection path derives from the file stem. The report records, per
installed file, its path and sha256, and for Copilot the instruction
listing.

## Integrations

- Copilot CLI 1.0.89: `copilot instruction list --json` needs a GitHub
  token but no model quota.
- Claude Code 2.1.280: unchanged.
- Anthropic Messages API: grader and verdict evaluator, unchanged.

## Failure Modes

- The Copilot projection is missing at the ref: exit 2 before any run.
- The instruction listing differs from the installed set: exit 2, the run
  would test leaked or missing instructions.
- Copilot model quota exhausted: verdict `ERROR`, exit 3, never a pass.
- The listing command fails or returns bad JSON: verdict `ERROR`, exit 3.
- A listing entry has no string `sourcePath`: exit 2, it could hide a leak.

## Security

No new trust boundary. The probe reuses the allowlisted environment in
`runtime_env`. No secret enters the report.

## Observability

The report carries the listing and the installed file hashes. The PR body
carries every run's command, exit code, and per-scenario result.

## Acceptance Criteria

1. When a fixture lists `instructions` and the harness is Copilot, the
   evaluator shall install each file's Copilot projection under
   `.github/instructions/` in the workspace.
2. When a Copilot projection is missing at the resolved ref, the evaluator
   shall exit 2 before any model call.
3. When a Copilot instruction fixture runs, the evaluator shall omit
   `--no-custom-instructions` and write no sentinel instruction file.
4. Before each Copilot instruction fixture runs, the evaluator shall compare
   the listing's `sourcePath` set with the installed set and exit 2 on any
   difference.
5. When the listing command fails, times out, or prints unparsable JSON,
   the evaluator shall report verdict `ERROR` and exit 3.
6. The report shall record the listing for each Copilot instruction fixture.
7. The scenario 10 and 13 fixtures shall judge the reply without requiring
   one exact phrase, and keep their controls and rubrics.
8. `scripts/eval/README.md` shall state the per-scenario threshold: ADR-057's
   two-of-three rule over at least three live runs.
9. The PR shall report base versus candidate results for scenarios 1 to 14,
   with model, harness, CLI version, source commit, and report hashes.
10. Each verdict scenario for #5404 shall grade the decision, not a synonym
    label or a phrase the prompt never asks for: critic `TC-1`, orchestrator
    `S11`, and orchestrator `S14` (which shall test scenario 6, handoff input).

## Out of Scope

- Persisted completion across compaction or handoff (#5417).
- New rule wording, unless a live run under the threshold fails.
- A `--runs` flag for the runtime evaluator.
- VS Code Copilot behavioral runs.

## Deferred

- Copilot live behavior while the model quota is exhausted. Owner: rjmurillo.

## Open Questions

None.

## CVA Summary

Common: both CLIs install an agent, load workspace instructions, and emit a
final reply. Varies: the install path and the isolation proof. Claude proves
isolation with a sentinel. Copilot proves it with the instruction listing.

## Buy-vs-build Decision

Core. Alternatives: keep refusing Copilot (fails the #5404 surface table),
or rely on the sentinel (cannot work, the loaded instructions include it).
Recommendation: build, using the CLI's own listing command.

## Complexity Classification

Tier 2. Domain: Complicated. Methodology: test-first on the harness, live
runs for behavior.
