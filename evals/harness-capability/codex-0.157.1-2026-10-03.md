# Codex 0.157.1 live probes for issue #5423

Run date: 2026-10-03. Harness: native `codex-cli 0.157.1`, model `gpt-5.6-sol`, effort `low`. Native login, agent-shims stripped from PATH. The matrix pins 0.156.0, so these captures move no cell.

## Pin check

| Item | Value |
|---|---|
| Installed codex | 0.157.1 |
| Matrix pin | 0.156.0 |
| Result | Mismatch recorded. No cell promoted. |

## Runs

Each row is one paid `codex exec` invocation. Children count inside their parent run.

| Run | Probe | Result |
|---|---|---|
| 1 | concurrency, `agents.max_threads=3`, parent does not wait | 3 children spawned, spawns 4 and 5 refused with `collab spawn failed: agent thread limit reached`. The parent finished first, so every child ended in `turn_aborted`. The reader cannot pair those turns, so no ceiling is derived. |
| 2 | concurrency, `agents.max_threads=3`, parent waits after the spawn attempts | 3 children admitted, 2 spawns refused. All 3 children closed their turns. Reader derives a ceiling of 3 to 3 with 2 refusals. |
| 3 | compaction, `model_auto_compact_token_limit=2000`, killed by an outer timeout | 4 `compacted` records. Turn left open, so the capture is partial. |
| 4 | compaction, same limit, bounded task | 2 `compacted` records, turns balanced, run completed. |

One further attempt (compaction, before stdin was closed) made no model call: `codex exec` printed `Reading additional input from stdin...` and waited. Redirect stdin from `/dev/null`.

## Reading

With the pin at 0.157.1, run 2 would verify `concurrency_limit` at 3 and run 4 would verify `context_reset_observability`. The test file `tests/eval/test_recorded_captures_codex_0_157_1.py` shows both. At the actual pin of 0.156.0 both stay `UNVERIFIED`. A re-pin needs every 0.156.0 cell re-probed, which this change does not do.

## Findings outside this change

- `_codex_rollout.peak_running_children` returns `None` when children end in `turn_aborted`. Run 1 shows a parent that does not wait always produces that. The classifier then reports "No rollout capture shows a spawn refused", although the parent rollout holds 2 refusals. The message names the wrong cause.
- Rollouts carry `creator_user_id`, `creator_account_id`, the working directory, and the base instructions. The fixtures here keep only the fields the readers use. The reduction is a filter over `session_meta`, `task_*`, `turn_aborted`, `context_compacted`, `turn_context`, `compacted`, and spawn-refusal outputs.

## Copilot

Owner direction on 2026-10-03: Copilot is dropped from eval support. The one probe made before that direction returned `You have exceeded your monthly quota` (GitHub routing, no model call served). The matrix no longer lists Copilot live probes as owed.
