# Claude Code 2.1.309 capability probe for issue #5426

Run date: 2026-10-23. Harness: native `claude` 2.1.309 (`2.1.309 (Claude Code)`). Every run used the operator's stored claude.ai subscription login. `claude auth status` reported `authMethod: claude.ai` and a `max` subscription. `ANTHROPIC_API_KEY` was not set. The probe environment removed `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, and the Bedrock, Vertex, and Foundry switches (`claude_routing_env` in `scripts/eval/_routing_claude.py`). Every captured `system/init` event read `apiKeySource: none`. No credential file was read, copied, or linked.

## Pin

The owner asked for a pin to 2.1.307, the version `claude --version` printed at the start of the session. The CLI auto-updated to 2.1.309 at 06:11 local time, between the fourth and fifth probe. The runs before the update were not kept as evidence, so every committed fixture is from 2.1.309 and the matrix pins `2.1.309 (Claude Code)`. The 2.1.307 binary stays under `~/.local/share/claude/versions/` and the probes did not use it.

An update can happen again. The runner sets `DISABLE_AUTOUPDATER=1`, and every result row carries the CLI version from `system/init`. After any update, run `claude --version`, re-probe every cell, and re-pin.

## Runs

23 top-level `claude -p` invocations, of a budget of 25. Retries and discarded runs count. No run returned a usage-limit or auth error. Children count inside their parent.

| Fixture (`tests/eval/fixtures/harness_capability/claude-2.1.309/`) | Cells it supports |
|---|---|
| `plan-writer`, `fresh-reader`, `effort-low` | model_override at the top level (opus, sonnet, haiku) |
| `subagent-haiku-child` | model_override, subagent_support, parent_child_override |
| `reviewer-isolation` | reviewer_isolation (none=NONE, all=ZEBRA-7731) |
| `plan-writer`, `fresh-reader` | fresh_session, single_agent, durable_artifact_handoff |
| `concurrency-cap3`, `concurrency-uncapped` | concurrency_limit VERIFIED at 3, 1 spawn refused; uncapped, 0 refused |
| `compaction`, `compaction-single-prompt` | context_reset_observability VERIFIED, 4 compactions; one oversized prompt cannot compact |
| `effort-low`, `effort-max`, `effort-ultra-ignored` | effort_override stays UNVERIFIED; sol_ultra UNSUPPORTED |
| `restricted-writes`, `acceptedits-outside-write`, `sandbox-unavailable` | permission mode choice (see below) |
| `ambient-audit` | ambient context audit |
| `invalid-model`, `usage-limit.synthetic` | failure shape, parser tests |

16 runs are kept as fixtures. 7 are discarded. Four ran on 2.1.307: a first ambient check, an effort pair, and a subagent attempt that used `--safe-mode` and so registered no custom agent. The other three ran on 2.1.309 and were superseded: a plan writer under `acceptEdits` with no `--restricted`, a first fresh reader, and a first ambient audit. `claude-2.1.309/effort-low` and `effort-max` count as two runs.

## Cell verdicts

| Cell | Status | Evidence |
|---|---|---|
| model_override | VERIFIED | Assistant messages name the requested id for opus, sonnet, and haiku. A haiku child under an opus parent names haiku. |
| effort_override | UNVERIFIED | The stream names no effort. See "How effort is observed". |
| subagent_support | VERIFIED | `Agent` call, forwarded child messages, `subagent_stats` spawned 1, completed 1. |
| concurrency_limit | VERIFIED, value 3 | `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS=3`: the fifth of five spawns was refused. Uncapped: none refused. |
| parent_child_override | VERIFIED | Parent opus, child haiku, `modelUsage` lists both. |
| reviewer_isolation | VERIFIED | The subagent whose prompt lacked the word answered NONE. The control answered ZEBRA-7731. |
| single_agent | VERIFIED | `--tools` without `Agent`: no `Task` in the init tools, `spawned` 0. |
| fresh_session | VERIFIED | A second `claude -p` had a new `session_id` and answered NONE for the writer's ticket. |
| durable_artifact_handoff | VERIFIED | `Write` created `implementation-plan.md`. A fresh session read `TOKEN: PLAN-4417`. |
| context_reset_observability | VERIFIED | 4 `compact_boundary` events with `--autocompact 100k`, all `success`. |
| sol_ultra | UNSUPPORTED | No ultra tier. The CLI ignores the value with a warning. |

Two cells need a caveat. subagent_support, parent_child_override, reviewer_isolation, and concurrency_limit measure the in-CLI subagent tool. The routing runner never uses it. Each runner invocation is its own `claude` process whose `--tools` list omits `Agent`, so fan-out, reviewer isolation, and concurrency are the runner's. The cells stay VERIFIED because the arm definitions require them and the capability exists. The concurrency control is an environment variable, and the runner does not set it. A runner row peaks at concurrency 1.

## How effort is observed

It is not. The stream carries no effort field. `system/init` has `per_turn_effort_active` (true for a valid model, false for the unknown model in `invalid-model`), and a debug log of a run with `--debug-file` named none. The `result` event, `usage`, and `modelUsage` carry no effort either.

One observed effect, one run each, `claude-haiku-5-5`, same arithmetic prompt, 2.1.309: 73 thinking tokens at `--effort low` and 279 at `--effort max`. An earlier pair on 2.1.307 read 77 and 228. The flag reaches the model. A token count does not show which value the backend served, so the cell is UNVERIFIED with `client_echo` evidence, and the runner records the requested effort as `UNVERIFIED`.

An unknown value is a trap. `--effort ultra` printed `Warning: Unknown --effort value 'ultra'` to stderr, then ran at the default effort and exited 0 (`effort-ultra-ignored`). The runner refuses any value outside `low`, `medium`, `high`, `xhigh`, `max`, and the parser fails a run whose stderr carries that warning.

## Permission mode

The runner uses `--restricted --permission-mode acceptEdits --tools Read,Edit,Write,Glob,Grep,Bash --allowedTools Read Edit Write Glob Grep 'Bash(python:*)' 'Bash(python3:*)' --permission-prompts none`.

- `acceptEdits` alone wrote `../outside.txt` from a workdir under `/tmp` (`acceptedits-outside-write`). It is not a workdir sandbox.
- `--restricted` refused that write ("outside the working directory") and denied `ls /` with no prompt (`restricted-writes`). It also refuses `bypassPermissions`.
- `--permission-prompts none` denies anything that would prompt, so a headless run cannot block on a prompt.
- Bash is limited to Python so a worker can run its checks. An allowed `python3 -c` call wrote `../outside2.txt` outside the workdir. This is the gap against Codex `-s workspace-write`, which is an OS sandbox. A model-generated Python command can write anywhere the user can.
- The Claude sandbox setting (`--settings '{"sandbox":{"enabled":true,"failIfUnavailable":true}}'`) failed every command with `nested userns is capability-restricted` on the probe host (`sandbox-unavailable`). It failed closed. Whether it works outside a nested sandbox is not known, so it is not used.

## Ambient context

Isolated, per the audit run through the final argv (`ambient-audit`): `CLAUDE.md` and rules, memory, skills, and hooks all read ABSENT. Every capture lists no skills, no MCP servers, no slash commands, and only built-in plugins.

Not isolated: the Claude Code built-in system prompt, the account email in the `userEmail` reminder, and the account display name in the `gitStatus` reminder. Setting `GIT_CONFIG_GLOBAL=/dev/null` did not remove the name, so it comes from the login and not from git. Every result row records this under `ambient_home`.

## Fixture reduction

Each stream keeps `system/init`, `assistant`, `user`, and `result` events. It drops `uuid`, `signature`, `capabilities`, rate-limit events, thinking-token progress events, `memory_paths`, and `output_file`. Thinking text is emptied. Session ids are rewritten to `session-<fixture>`, workspace paths to `/work`, and other scratch paths to `/scratch`. The operator name, email, and handle are replaced with `<operator-name>`, `<operator-email>`, and `<operator-handle>`. The compaction stream keeps only `system` and `result` events and trims each `compact_boundary` to trigger and token counts. The fixtures were searched for the home path, the operator name, email patterns, the org id, and raw session ids. None matched. `effort-ultra-ignored.stderr.txt` is a verbatim capture and holds one U+2014 byte from the CLI warning.

`usage-limit.synthetic.stdout.jsonl` is not a capture. A usage-limit refusal was not induced. It copies the shape of the real `invalid-model` error and carries a stand-in message, and its first event says so.

## Arm eligibility

Claude is `"standalone": true` in the matrix. It is no peer for Codex and Codex is none for it, so each reaches at most `ELIGIBLE_UNMATCHED` and Codex keeps the classes it had.

| Arm | claude | Why |
|---|---|---|
| A, C, D, E | UNVERIFIED | They require a verified `effort_override`. |
| B, F | ELIGIBLE_UNMATCHED | They do not require it. |

A lone Claude harness cannot reach A, C, D, or E until effort is observed.

## Findings outside this change

- `--bare` skips OAuth and keychain reads and needs `ANTHROPIC_API_KEY`, so it cannot run on the subscription login.
- `--safe-mode` also disables custom agents passed with `--agents`.
- `claude auth status` printed `forcedLoginMethod: console` for the operator's settings while the active login is claude.ai. The runner ignores user settings and every stream read `apiKeySource: none`.
- `result.total_cost_usd` is a notional list price on a subscription login. The routing result rows also compute `cost_usd` from `_eval_common` rates, and `claude-opus-5-5` has one. Amendment 3 treats cost as unpriced and no verdict reads it.
- `result.subtype` stays `success` on an error result. The error is in `is_error`, `api_error_status`, and the `result` text.
