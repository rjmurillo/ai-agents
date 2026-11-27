# Supported harnesses

This file is the single source of truth for harness support in `skill-doctor`. Reference it instead of repeating harness lists in `SKILL.md`.

## Operating systems

Collection and rendering run on Linux, macOS, and Windows with python3 and its standard library.
Filesystem discovery uses native paths and the user's configured home directories.
Copilot's CLI flag overrides `COPILOT_HOME`, which overrides the default home directory.
The default is `~/.copilot` on POSIX and `%USERPROFILE%\.copilot` on Windows.
Warp discovery uses macOS group containers, Linux XDG data directories, or Windows `%APPDATA%\Warp`.
Use `--warp-data-dir` or `--warp-db` for nonstandard Warp storage.
Repository filtering recognizes POSIX, Windows drive, and Windows UNC journal paths.
Windows path comparisons ignore case; POSIX path comparisons preserve case.
The upstream repository-name fallback can still match unrelated repositories sharing a name.
Inventory files, transcripts, and HTML use UTF-8 on every OS.
Unencodable diagnostic characters are escaped when a legacy output encoding requires it.

## Startup gate

| Harness | Collector ID | Local conversation source |
| --- | --- | --- |
| Warp | `warp` | Read-only Warp conversation databases |
| Claude Code | `claude` | Project-history JSONL |
| Codex | `codex` | Rollout JSONL |
| GitHub Copilot CLI | `copilot` | `session-state/<id>/events.jsonl` |
| Pi | `pi` | Pi agent JSONL (`~/.pi/agent/sessions`) |
| Grok Build | `grok` | Grok Build chat_history JSONL (`~/.grok/sessions`) |
| ZCode | `zcode` | ZCode model-io rollout (`~/.zcode/cli/rollout`) |
| Hermes | `hermes` | Hermes Agent state.db (SQLite: `sessions` + `messages`) |
| Factory Droid | `droid` | Droid session JSONL (`~/.factory/sessions/<encoded-cwd>/<id>.jsonl`) |
| Muse | `muse` | Muse session JSONL (`~/.local/share/muse/sessions/YYYY/MM/DD/<id>/session.jsonl`) |

Known but unsupported, with no collector:

- Devin CLI keeps history in `~/.local/share/devin/cli/sessions.db` (SQLite tables `sessions`, `message_nodes`, `tool_call_state`). The store held 0 rows on the machine that was inspected, so no parser could be tested against real data. A collector needs a populated fixture first.
- Antigravity scoring: its text transcripts carry no tool calls, so they never reach scoring. They read as a corpus-only source, below.

Sessions from these harnesses never reach the report. Do not read their stores by hand.

## Corpus-only sources

Two sources feed `--export-corpus` and nothing else. They hold conversation text with no tool calls, so the collector never scores them. With `--export-corpus` unset, the collector does not read them, and its output is unchanged.

| Source | Collector ID | Local conversation source |
| --- | --- | --- |
| T3 Code | `t3` | Read-only, immutable SQLite `~/.t3/userdata/statev2.sqlite`: `orchestration_v2_projection_threads` and `orchestration_v2_projection_messages` |
| Gemini antigravity | `gemini` | `~/.gemini/antigravity-cli/brain/<id>/.system_generated/logs/transcript_full.jsonl` |

- `--t3-home PATH` (default `~/.t3`) and `--gemini-home PATH` (default `~/.gemini/antigravity-cli`) override the homes.
- `--harness auto` and `--harness all` read a source when it exists and skip it when it does not. `--harness t3` or `--harness gemini` needs `--export-corpus` and exits 2 when the source is missing.
- Neither source records a working directory, so the repository filter drops them. Pass `--all-conversations` to export them.
- A T3 database that lacks a required table or column counts as `schema_mismatch` in `collection_issues`. An unreadable database counts as `database_failures`. Neither stops the run.

At startup, identify the harness executing the skill from the runtime context. Do not infer it from conversation files found on disk.

If the executing harness is not listed above, or cannot be identified confidently, stop before creating a report directory or reading conversation history. Tell the user:

> This harness is unsupported or unidentified. No conversations were read. See the table above.

## Collector source selection

- `--harness auto` scans every locally available supported source and is the default.
- `--harness all` also requests every supported source.
- `--harness <collector-id>` restricts collection to one source from the table.
- A report containing one source uses its collector ID in `inventory.json`; a report containing multiple sources uses `mixed`.

Harness-specific source overrides:

- `--claude-home PATH` - nonstandard Claude Code configuration directory.
- `--codex-home PATH` - nonstandard Codex home.
- `--copilot-home PATH` - Copilot home containing `session-state`.
  Defaults to `COPILOT_HOME`, then `~/.copilot`.
- `--warp-db PATH` - explicit Warp database; repeatable.
- `--warp-data-dir PATH` - nonstandard Warp channel-data directory.
- `--pi-home PATH` - nonstandard Pi agent home (default `~/.pi/agent`).
- `--grok-home PATH` - nonstandard Grok Build home (default `~/.grok`).
- `--zcode-home PATH` - nonstandard ZCode home (default `~/.zcode`).
- `--factory-home PATH` - nonstandard Factory Droid home containing `sessions` (default `~/.factory`).
- `--hermes-home PATH` - Hermes Agent home containing `state.db` (default discovery checks `HERMES_HOME`, `~/.hermes`, then `~`).
- `--muse-home PATH` - Muse data home containing `sessions` (default `MUSE_HOME`, then `~/.local/share/muse`).

## Skill locations

Project skills are discovered from:

- `.claude/skills`
- `.codex/skills`
- `.github/skills`
- `.factory/skills`

Other repository skill directories require an explicit `--skills-dir PATH`.
Global discovery includes each harness's standard skill directory when
`--include-global-skills` is set.
This includes Claude Code, Codex, Pi, Grok Build, ZCode, Factory Droid, and Hermes homes.
The collector's `discover_skills` function defines the exact search roots.

Copilot also scans `<copilot-home>/skills` and
`<copilot-home>/installed-plugins/*/*/skills` when global discovery is enabled.

Muse also scans `<muse-home>/skills`,
`<muse-home>/plugins/cache/*/*/*/package/skills`, the Muse config home
skills directory (default `$XDG_CONFIG_HOME/muse/skills` or
`~/.config/muse/skills`, override with `--muse-config-home`), and
the shared agents home skills directory when global discovery is enabled.
Project skills under a repository's shared agents directory are not scanned
automatically; pass that directory with `--skills-dir`.

Identical definitions share one content fingerprint and keep every path as an alias.
Different same-name definitions all stay discoverable and count toward usage and coverage.
The first definition found is the current edit target: `--repo` paths in order, then global homes, then `--skills-dir` directories.
The inventory lists conflicts under `skill_variants` and counts them in `stats.ambiguous_skills`.
That count is information, not a collection failure.
Historical attribution stays `unresolved` for a conflicting name.
A transcript does not record which bytes ran, so a fingerprint is never the executed version.

## Project boundaries and collection losses

Project filtering requires native absolute paths inside explicitly selected repositories.
Matching checkout names never grants access to another checkout.
Select each authorized checkout using another `--repo PATH`.
Foreign-platform paths cannot match a native project selection.
An all-conversation run requires separate user authorization.

Malformed records, unreadable sources, and schema failures increment `collection_issues`.
Nonempty counters mark `collection_status` as `partial` and produce one stderr summary.
Healthy records remain available; partial collection is not evidence of absent usage.
Replay, child-session, scope, and sampling exclusions are not collection failures.

## Copilot event handling

The collector streams persisted events, skipping replay checkpoints and transient events.
It reads session context, messages, tool starts, tool completions, and skill invocations.
It ignores model snapshots, instructions, skill catalogs, and streaming deltas.
Tool starts provide call counts, arguments, edit hints, and repeated-call detection.
Explicit failure flags and error messages provide error-output counts.
Skill names come from `skill.invoked` and tool arguments, not catalog descriptions.
Only discovered installed skills enter the final usage inventory.
A `namespace:name` invocation counts as usage of installed `name`.
The namespace is not matched to a definition. When the qualified name is the only evidence in the transcript, the session's `skill_attribution` records `namespace_unverified`.
Only the `skill` and `bundled_skill_id` keys count as a qualified invocation. A generic `name` value such as `area:review` does not.
`skill_attribution` lists `unresolved_because` as `conflicting_definitions`, `namespace_unverified`, or `evidence_not_in_transcript`.
The last one means the bounded transcript no longer shows how the skill was named.

Events marked with `agentId` or `data.parentToolCallId` are treated as child events.
They are excluded unless `--include-subagents` is passed.
Included child events remain part of their parent session transcript.
The session directory supplies the output identifier, never an untrusted event path.

Storage verified against Copilot CLI 1.0.108-1 on 2026-11-09.
Event field shapes were checked against this CLI's local journal.
These journal fields are version-sensitive, not a promised stable API.
These are CLI journals, not GitHub cloud coding-agent logs.

## Muse event handling

The Muse journal is event-sourced. Each `session.jsonl` line carries a
`payload_type` and `payload`; the first line can wrap child records as JSON
strings under `children[].record_json`. The collector reads
`runtime.session.metadata` and `runtime.session.route_facts` for the workspace,
`runtime.user_intent.accepted` for user prompts, run records for assistant
prose (`assistant_message_committed`), tool calls with arguments
(`assistant_tool_calls_committed`), outputs (`tool_result_batch_committed`),
and per-response completion (`model_completed`), plus
`tool_batch.effect.started` / `tool_batch.effect.terminal` for tool names and
outcomes. Each tool call is emitted once, with arguments when a run record
names the same `call_id`. Timestamps are epoch microseconds in `recorded_at`.

Some records are marked omitted in the journal and never reach the collector.
`assistant_turns` counts distinct run ids. A session is scoreable only when it
has at least one assistant turn and at least one tool call. Skill names come
from tool arguments
(`read_skill` takes `{"name": ...}`), so journals without run records report
no detected skill usage.

Storage verified against Muse 1.4.25 on 2026-11-22. Run-event mapping
verified against 1.4.15 and 1.4.25 journals on 2026-11-23.
These journal fields are version-sensitive, not a promised stable API.
