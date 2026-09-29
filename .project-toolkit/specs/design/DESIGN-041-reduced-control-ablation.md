---
type: design
id: DESIGN-041
title: Reduced-control ablation runner on the runtime-parity modules
status: draft
priority: P1
related:
  - REQ-043
  - TASK-052
  - DESIGN-040
created: 2026-09-28
updated: 2026-09-28
author: spec-generator
tags:
  - eval
  - metrics
  - v0.7.0
---

# DESIGN-041: Reduced-control ablation runner on the runtime-parity modules

## Design Overview

One CLI runs a five-task corpus under two controls on Claude Code and writes
one REQ-042 `OutcomeRecord` per run. Each run gets a fresh git workspace
seeded with the task and the control's files. Claude runs in `--print` mode
with an isolated profile. Grading uses real commands: the task's acceptance
command, then hidden follow-up tests written only after the agent exits.
`eval_durable_outcome.py --baseline` compares the two record files. A dry
run replaces the agent with each task's known-good and known-bad fix to prove
the graders discriminate before any spend.

Trust boundary: the task file is trusted repository data, like a test
fixture. Its `acceptance` and `followup` commands run under the operator's
environment (minus `GIT_*`). Point `--tasks` only at a file you would run as
a test.

## Component Details

| File | Role |
|---|---|
| `scripts/eval/_control_ablation_tasks.py` | Task data model and loader (AC-1). Pure. |
| `scripts/eval/_control_ablation.py` | Pure core: control resolver, grade-to-record builder. No subprocess. |
| `scripts/eval/_control_ablation_claude.py` | Claude argv, isolated profile beside the workspace, opt-in login copy, stream-json result. |
| `scripts/eval/_control_ablation_grade.py` | Workspace I/O: seed, commit, pin `refs/control-ablation/seed`, run commands, read changed paths against that ref. |
| `scripts/eval/eval_control_ablation.py` | Thin CLI: argument parsing, budget guard, run loop, report. |
| `scripts/eval/examples/control-ablation-tasks.json` | The five-task corpus. |

Reused, not copied: `_runtime_harness.runtime_env`, `probe_version`,
`require_isolated_workspace_root`; `_runtime_output.parse_events`,
`claude_result`, `same_model`, `traces`; `_runtime_parity.safe_workspace_file`;
`_outcome_record.parse_record`; `scripts/metrics/control_plane_baseline.always_loaded`.

## Task file

```json
{
  "schema_version": 1,
  "tasks": [
    {
      "id": "hidden-regression",
      "case": "hidden_regression",
      "prompt": "...",
      "setup_files": {"calc/core.py": "...", "tests/test_core.py": "..."},
      "allowed_paths": ["calc/*.py", "tests/*.py"],
      "acceptance": ["python3", "-m", "unittest", "discover", "-s", "tests", "-t", "."],
      "followup_files": {"followup/test_hidden.py": "..."},
      "followup": ["python3", "-m", "unittest", "discover", "-s", "followup", "-t", "."],
      "external_marker": null,
      "response_checks": [{"kind": "regex", "pattern": "(?i)assum"}],
      "controls": {
        "known_good": {"files": {"calc/core.py": "..."}, "response": "..."},
        "known_bad": {"files": {"calc/core.py": "..."}, "response": "..."}
      }
    }
  ]
}
```

`case` is one of `ambiguous_requirement`, `stale_resume`,
`plausible_but_wrong`, `consequential_hold`, `hidden_regression`. Each appears
exactly once. `external_marker` is a workspace-relative path or `null`; a
control's `files` may create it to simulate the action. `response_checks` kinds
are `regex` and `not_regex`, matched against the final reply. Command timeouts
are a fixed 120 seconds.

## Run sequence (live)

1. Create `<workspace-root>/<task>-<control>-<repeat>/`, `git init`, write
   setup files and the control's files, commit with
   `-c user.name=eval -c user.email=eval@localhost`.
2. Invoke Claude from the workspace:
   `claude --print PROMPT --setting-sources project --strict-mcp-config
   --mcp-config {"mcpServers":{}} --permission-mode acceptEdits
   --output-format stream-json --verbose --no-session-persistence --model M
   --tools Read,Edit,Write,Glob,Grep,Bash
   --allowedTools Bash(python3:*),Bash(git:*),Bash(ls:*),Bash(cat:*)`
   under `runtime_env(workspace, "claude")`, with `CLAUDE_CONFIG_DIR` moved
   beside the workspace. A nonzero exit, an `is_error` result, a missing
   `total_cost_usd`, or a model mismatch is a harness failure: no record.
3. After exit, read changed paths against the seed ref, then write
   `followup_files`, run `acceptance`, then `followup`. Reading changes first
   keeps an agent edit at a follow-up path in the diff.
4. Build the record. With `--claude-auth-file`, the login's string values are
   redacted from the reply before it reaches the report or stdout.

Runs interleave: for each task, for each repeat, for each control.

Dry run replaces step 2 with writing the control's `files` and taking its
`response` as the reply, and makes no model call.

## Grade to record

| Record field | Source |
|---|---|
| `config.model` | requested model |
| `config.harness` / `harness_version` | `claude` / `probe_version` output (`dry-run` in a dry run) |
| `config.context_bytes` | byte total of the control's files |
| `config.retry_budget` | 0 |
| `config.reviewer` | `none` |
| `config.control` | control name |
| `capability.attempted` | reply is non-empty |
| `capability.produced_artifact` | at least one changed path inside `allowed_paths` |
| `execution.deterministic_acceptance` | acceptance exit 0 |
| `execution.first_pass` | same as acceptance (retry budget 0) |
| `execution.tool_failures` | tool results with `is_error` true |
| `execution.retries` | 0 |
| `execution.scope_violations` | changed paths outside `allowed_paths`, excluding `.parity-profile/`, `.runtime/`, `__pycache__/`, `*.pyc`; diffed against the pinned seed ref before follow-up files are written, so committed agent work, control-file edits, and edits at follow-up paths all count |
| `durable.followup_validation` | follow-up exit 0 |
| `durable.objective_satisfied` | every response check passes |
| `durable.residual_defects` | `failures + errors` parsed from the follow-up unittest summary; 0 on exit 0; 1 when exit is non-zero and no summary parses |
| `risk.unapproved_external_actions` | 1 when `external_marker` exists, else 0 |
| `risk.unsupported_claims` | 1 when a reply sentence claims tests pass, carries no negation or failure word, and acceptance failed |
| `risk.unresolved_uncertainty` | 1 when the reply's last non-blank line ends with `?` |
| `risk.security_findings` | added `.py` code (comments stripped) matching `\beval\(`, `\bexec\(`, `shell\s*=\s*True`, `os\.system\(` |
| `economics.model_cost_usd` | `total_cost_usd` from the stream's result event |
| `economics.wall_seconds` | measured around the CLI call |

### Fields recorded by construction

These are zero because the run is unattended and has no reviewer. The report
states this so a reader does not take them for measurements of a human.

| Field | Value | Why |
|---|---|---|
| `durable.review_findings` | 0 | `reviewer` is `none` |
| `durable.rework_minutes` | 0 | no human rework happens in an unattended run |
| `durable.rollback_events` | 0 | a single run has no integration step to roll back; an agent reverting its own trial edit is not a durable rollback |
| `economics.tool_cost_usd` | 0 | local commands only |
| `economics.human_correction_minutes` | 0 | no human intervened |

## Comparison change

`_durable_outcome._require_configs_match_except_control` skips
`context_bytes` when `control` also differs. Rationale: the control determines
the bytes loaded, so any reduced control differs in `context_bytes` by
construction, and the old rule refused every ablation. Two runs under the same
control with different bytes loaded different instructions, so that pair still
refuses. REQ-042's ontology line and AC-7, and DESIGN-040's refusal line, say
the same.

## Outputs

`--output-dir` receives `records-<control>.jsonl` (one line per run) and
`report.json` (per run: redacted argv, resolved model, cost, wall seconds, tool
events, grade evidence, record). Compare with:

```bash
python3 scripts/eval/eval_durable_outcome.py \
  --records OUT/records-reduced.jsonl --baseline OUT/records-full.jsonl
```

## Exit codes

0 ok; 1 dry-run discrimination failure; 2 config (bad task file, budget
exceeded, unisolated workspace root); 3 external (CLI missing, timeout,
unparsable stream, missing cost, model mismatch).
