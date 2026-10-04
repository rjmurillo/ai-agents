# Codex 0.160.0 re-probe for issue #5423

Run date: 2026-10-03. Harness: native `codex-cli 0.160.0` (the installed version, read with `codex --version`). Native login in the operator's own `CODEX_HOME`. No credential file was linked, copied, or read. Agent-shims stripped from PATH.

## Pin

The matrix pin tracks the installed CLI. A codex auto-update invalidates it: the CLI moved from 0.156.0 to 0.157.1 to 0.160.0 in one day. After any update, run `codex --version`, re-probe every codex cell, and re-pin. A cell cites fixtures from the version it names.

## Runs

Each row is one top-level `codex exec`. Children count inside their parent. Commands are the `probe_command` fields in `scripts/eval/examples/harness-capability-matrix.json`.

| Fixture (`tests/eval/fixtures/harness_capability/codex-0.160.0/`) | Cells it supports |
|---|---|
| `subagent-luna-high` | model_override, effort_override, subagent_support, parent_child_override |
| `reviewer-isolation` | reviewer_isolation (none=NONE, all=ZEBRA-7731) |
| `plan-writer`, `fresh-session-handoff` | fresh_session, single_agent, durable_artifact_handoff |
| `sol-6-low`, `luna-high` (gpt-5.6-luna), `terra-high` | top-level model and effort |
| `sol-6-ultra`, `sol-5.6-ultra`, `models-catalog.json` | sol_ultra stays UNVERIFIED: the backend reports effort `max` for an ultra request |
| `concurrency-cap3-wait` | concurrency_limit VERIFIED at 3, 2 spawns refused |
| `concurrency-cap3-nowait` | parent does not wait: children end in `turn_aborted`, no ceiling read |
| `concurrency-3-requested`, `thread-limit-1` | uncapped children never overlapped; a cap of 1 refused the second spawn |
| `compaction-limit2000` | context_reset_observability VERIFIED, 4 `compacted` records |

14 top-level invocations. The `luna-high` run used `gpt-5.6-luna`, not `gpt-6-luna` as in 0.156.0, because the arms name 5.6 models.

## Fixture reduction

Trace logs keep only `response.created`, `response.output_item.done`, and `response.completed` frames, with `tools` and `instructions` dropped from `response` (0.160.0 frames carry them and each log was 1 MB). Rollouts keep `session_meta` (id, timestamp, cli_version, source), task and compaction events, `turn_context` (turn id, model, effort), and spawn-refusal outputs. Account ids, working directories, and base instructions are not kept. The workspace path in stdout is rewritten to `/work/`.

## Arm eligibility

Copilot is dropped (`"dropped": true` in the matrix). A dropped harness reads UNSUPPORTED and is nobody's peer. A lone active harness can reach `ELIGIBLE_UNMATCHED` and never `ELIGIBLE_MATCHED`, because no comparison across harnesses exists. With this matrix every codex arm A to F reads `ELIGIBLE_UNMATCHED`.

## Findings outside this change

- `_codex_rollout.peak_running_children` returns `None` when children end in `turn_aborted`. The nowait run holds spawn refusals in its parent and the classifier still reports "No rollout capture shows a spawn refused". Tracked in an issue.
- `codex exec` printed `Reading additional input from stdin...` even with stdin from `/dev/null`. It did not hang.
