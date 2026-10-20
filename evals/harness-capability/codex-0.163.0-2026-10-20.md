# Codex 0.163.0 re-probe for issue #5426

Run date: 2026-10-20. Harness: native `codex-cli 0.163.0` (the installed version, read with `codex --version` before the first probe and after the last; it did not change). Native login in the operator's own `CODEX_HOME`. `codex login status` reported "Logged in using ChatGPT". Every probe ran on the ChatGPT subscription login with `OPENAI_API_KEY`, `CODEX_API_KEY`, and `OPENAI_BASE_URL` unset in the probe environment. No credential file was linked, copied, or read. No agent-shim was on PATH.

## Pin

The matrix pin tracks the installed CLI. A codex auto-update invalidates it. After any update, run `codex --version`, re-probe every codex cell, and re-pin. A cell cites fixtures from the version it names. The 0.160.0 and 0.157.1 fixtures stay as history.

## Runs

Each row is one top-level `codex exec`, stdin from `/dev/null`. Children count inside their parent. Commands for the cells are the `probe_command` fields in `scripts/eval/examples/harness-capability-matrix.json`. The `nowait`, `concurrency-3-requested`, and `thread-limit-1` prompts are not matrix fields; they are listed below.

| Fixture (`tests/eval/fixtures/harness_capability/codex-0.163.0/`) | Cells it supports |
|---|---|
| `subagent-luna-high` | model_override, effort_override, subagent_support, parent_child_override |
| `reviewer-isolation` | reviewer_isolation (none=NONE, all=ZEBRA-7731) |
| `plan-writer`, `fresh-session-handoff` | fresh_session, single_agent, durable_artifact_handoff |
| `sol-6-low`, `luna-high` (gpt-5.6-luna), `terra-high` | top-level model and effort |
| `sol-6-ultra`, `sol-5.6-ultra`, `models-catalog.json` | sol_ultra stays UNVERIFIED: the backend reports effort `max` for an ultra request |
| `concurrency-cap3-wait` | concurrency_limit VERIFIED at 3, 2 spawns refused |
| `concurrency-cap3-nowait` | parent does not wait: children end in `turn_aborted`, no ceiling read |
| `concurrency-3-requested`, `thread-limit-1` | uncapped gpt-5.6-luna children overlapped at 3; a cap of 1 refused the second spawn |
| `compaction-limit2000` | context_reset_observability VERIFIED, 3 `compacted` records |

14 top-level invocations. `models-catalog.json` comes from `codex debug models`, which makes no model call.

Prompts that are not matrix fields:

- `nowait`: the `cap3-wait` prompt with the last sentence replaced by "Do not wait for any child; reply as soon as all spawns are attempted."
- `concurrency-3-requested`: "Spawn exactly 3 subagents one after another, each using model gpt-5.6-luna with fork_turns none, each told to write 300 words about a river and then reply with its index. Do not wait on any before spawning all 3. Then wait for every child to finish and reply with the three indexes." No thread cap.
- `thread-limit-1`: `-c agents.max_threads=1`, "Spawn 2 subagents one after another with fork_turns none, each told to reply with its index. Do not wait on any before spawning both. Reply with each spawn result or the exact spawn error. Then wait for every spawned child to finish before you reply."

## What changed from 0.160.0

- Uncapped fan-out: 3 requested gpt-5.6-luna children overlapped at a peak of 3. The 0.160.0 capture peaked at 1, but it requested gpt-6-luna children, so model and version both differ. No like-for-like run was made.
- Compaction: 3 `compacted` records, not 4, with the same limit of 2000 and a different workspace (7 small files).
- Durable handoff: the writer ran no verification command, so the capture shows the file path and not the content. The test now relies on the fresh session answering `plan=PLAN-4417` with no prior context, and the file on disk was checked after the run.
- Unchanged: model and effort overrides, parent and child override, subagent support, cap of 3 with 2 refusals, reviewer isolation, single agent, fresh session, ultra reported as effort `max`.

## Fixture reduction

Trace logs keep only `response.created`, `response.output_item.done`, and `response.completed` frames, with `tools`, `instructions`, `safety_identifier`, and `user` dropped from `response`. Rollouts keep `session_meta` (id, timestamp, cli_version, source, thread_source), task and abort events, `turn_context` (turn id, model, effort), emptied `compacted` records, and spawn-refusal outputs. Account ids, working directories, and base instructions are not kept. The workspace path in stdout is rewritten to `/work/`. The fixtures were searched for the home path, the operator name, email patterns, account and creator fields, and token strings; none matched.

## Arm eligibility

Copilot stays dropped (`"dropped": true` in the matrix). A lone active harness reaches `ELIGIBLE_UNMATCHED` and never `ELIGIBLE_MATCHED`. The routing benchmark dry run plans 36 codex rows, all `PLANNED` and `ELIGIBLE_UNMATCHED`, with `harness_version` `codex-cli 0.163.0`.

## Findings outside this change

- `evals/routing-benchmark/results-2026-10-03/README.md` and `evals/durable-outcome-live/README.md` name 0.160.0. They are dated records and were left as they are.
- `codex exec` prints `Reading additional input from stdin...` unless stdin is redirected. Probes used `/dev/null`.
