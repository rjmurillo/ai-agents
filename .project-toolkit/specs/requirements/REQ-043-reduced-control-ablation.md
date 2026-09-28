---
type: requirement
id: REQ-043
title: Compare the full control plane with a reduced one on identical code tasks
status: draft
priority: P1
category: functional
source: issue-5768
related:
  - DESIGN-041
  - TASK-052
  - REQ-042
  - REQ-022
created: 2026-09-28
updated: 2026-09-28
author: spec
tags:
  - eval
  - metrics
  - v0.7.0
---

# REQ-043: Compare the full control plane with a reduced one on identical code tasks

## Step 0 First Principles

### Q1 Demand Reality

Issue #5768, filed by rjmurillo under epic #5456, asks to "Compare the current
configuration with at least one reduced-control configuration under the same
tasks, model/harness version, and retry/correction budget." Epic #5456 release
gates 5, 6, and 7 need the same comparison. PR #5978 shipped the record and the
comparison, and its body says the live experiment "is not in this diff."

### Q2 Status Quo

Nobody can run the comparison today. `eval_durable_outcome.py` compares two
JSONL files, but no tool produces the records. `eval_runtime_parity.py` runs a
real CLI in an isolated repository, but it grades a reply and a file, not a
code change, and it cannot run a test command.

### Q3 Desperate Specificity

The v0.7.0 release. Its ledger row for gate 5 reads "No run data yet"
(`.project-toolkit/metrics/control-plane-dispositions-v0.7.0.md`, gate 5 row).

### Q4 Narrowest Wedge

One CLI that runs a small task corpus under two controls on one harness,
grades each run with commands, and writes REQ-042 records. About 600 lines of
code and tests plus five task fixtures. Claude Code only (user decision D2).

### Q5 Observation

The pinned baseline records `accepted_tasks.verified: 0` of 22
(`.project-toolkit/metrics/control-plane-baseline-v0.7.0.json`). Gates 5 to 7
are "Unchecked" in the ledger's release gate table.

### Q6 Future-fit

At 10x tasks the corpus grows as data, not code. A second harness adds one argv
builder. The `--max-runs` guard keeps spend bounded as the corpus grows.

## Prior art searched (Step 0.5)

- `scripts/eval/eval_runtime_parity.py` and `_runtime_harness.py`: isolated
  workspace, allowlisted env, Claude argv, stream-json parsing. Reused.
- `scripts/eval/_outcome_record.py`, `_durable_outcome.py`: the record and the
  comparison. Reused as the output contract.
- `scripts/metrics/control_plane_baseline.py::always_loaded`: the canonical list
  of files Claude Code always loads. Reused to define the `full` control.
- Issue #5424 runner: no code exists. User decision D1 chose this path instead.

No halt: nothing in the tree already runs a code task under two controls.

## Problem statement

v0.7.0 must prove that a smaller control plane delivers at least as much
accepted durable work. No tool runs the same code tasks under the full and a
reduced control plane and records the outcome.

## User stories

- As the release owner, I run one command and get two JSONL files that
  `eval_durable_outcome.py --baseline` compares, so gates 5 to 7 carry data.
- As a reviewer, I run a zero-spend dry run that proves each task's grader
  tells a known-good fix from a known-bad one.

## Ontology

- **Task**: one code change request with seeded files, an allowed path set, an
  acceptance command, hidden follow-up files and command, and response checks.
- **Control**: a named set of repository files installed into the workspace.
  `full` is `always_loaded(...)["claude_code"]["files"]`. `reduced` is empty.
- **Run**: one Task under one Control, one repeat. It yields one
  `OutcomeRecord` (REQ-042).
- **Grade**: the deterministic evidence read from the workspace after the run.

## Data model

Task file, `schema_version: 1`, shape in DESIGN-041. Invariants: task ids are
unique; every task names one of the five #5768 cases; every case appears once;
`allowed_paths` is non-empty; follow-up files never exist before the agent run.

## Integrations

Claude Code CLI, invoked shell-free with `--print` and `stream-json`. Failure
modes: timeout, non-zero exit, unparsable stream, missing `total_cost_usd`,
resolved model differs from requested. Each is a harness failure, exit 3, and
no record is written for that run.

## Failure modes

- Ancestor instruction files leak into the workspace: refused before any run,
  reusing `require_isolated_workspace_root`.
- Spend overrun: refused before any run when tasks x controls x repeats exceeds
  `--max-runs` (default 30).
- Drift between controls over wall time: runs interleave controls per task and
  repeat.
- A grader that always passes: the dry run fails when `known_bad` classifies
  `ACCEPTED_DURABLE` or `known_good` does not.

## Security

The agent runs with `--permission-mode acceptEdits` and a Bash allowlist of
`python3`, `git`, `ls`, and `cat`. The env is `runtime_env(..., "claude")`, an
allowlist. Task text is public test data. No credential is written to a report.
The `stream-json` output is stored raw, so it must not carry the auth token;
Claude Code does not echo it.

## Observability

The report JSON keeps per run: argv (redacted), resolved model, cost, wall
seconds, tool events, grade evidence, and the record. The metric that proves
this works is the dry run: 5 of 5 `known_good` accepted durable, 0 of 5
`known_bad` accepted durable.

## Acceptance criteria

1. AC-1: When the task file is loaded, the loader shall refuse (exit 2) a
   duplicate id, an unknown case, a missing case, an empty `allowed_paths`, a
   follow-up file that is also a setup file, and an unknown key.
2. AC-2: When `--dry-run` runs, the CLI shall apply each task's `known_good` and
   `known_bad` controls, grade them with the real commands, and exit 1 if any
   `known_good` is not `ACCEPTED_DURABLE` or any `known_bad` is.
3. AC-3: When a live run is requested and tasks x controls x repeats exceeds
   `--max-runs`, the CLI shall exit 2 before invoking any model.
4. AC-4: When a run finishes, the grader shall write follow-up files only after
   the agent exits, then set `followup_validation` from the follow-up exit code
   and `residual_defects` from its failed plus errored test count.
5. AC-5: When a changed path falls outside `allowed_paths`, the grader shall
   count it in `scope_violations`. Control files, the profile, and follow-up
   files are excluded from the count.
6. AC-6: When the task's external-action marker file exists after the run, the
   grader shall set `unapproved_external_actions` to 1.
7. AC-7: When the reply claims tests pass and the acceptance command failed,
   the grader shall set `unsupported_claims` to 1.
8. AC-8: When the Claude stream lacks `total_cost_usd`, or the resolved model
   differs from the requested one, the run shall be a harness failure (exit 3)
   with no record written.
9. AC-9: The `full` control shall be the file list
   `control_plane_baseline.always_loaded` returns for `claude_code`, installed
   at the same repository-relative paths; `context_bytes` shall be those files'
   byte total.
10. AC-10: When `compare` receives two configs that differ only in `control` and
    `context_bytes`, it shall compare them; any other difference still refuses.
11. AC-11: Every live run shall emit one record that `parse_record` accepts, in
    `records-<control>.jsonl` under `--output-dir`.

## Out of scope

- Copilot and Codex harnesses (user decision D2).
- The #5424 six-arm routing runner and the #5422 routing verdict.
- A model judge. Every field is deterministic or recorded as zero by
  construction (see DESIGN-041, "Fields recorded by construction").
- An independent reviewer stage.

## Deferred

- A second harness: owner #5423 and #5424.
- `context_bytes` from a #5400 measurement: owner #5400.

## Open questions

None. Claude auth for the isolated profile was open; it is resolved by the
opt-in `--claude-auth-file` flag (operator decision 2026-09-28: use the
installed subscription CLIs, no extra API keys).

## CVA summary

Common: every run installs a control, runs the agent, and grades with commands.
Varies: the control's file set and the task data. Relationship: tasks and
controls are data; one grader serves all of them.

## Buy-vs-build decision

Context, not core. Alternatives: the #5424 runner (no code, blocked on
Copilot quota, user rejected in D1); an external eval framework (a second
record format). Recommendation: build a thin CLI on the shipped runtime-parity
modules and the REQ-042 record.

## Complexity classification

Tier 3. Domain: Complicated. Methodology: test-first on the pure grader and
loader, dry-run proof before any spend.
