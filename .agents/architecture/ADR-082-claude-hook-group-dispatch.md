# ADR-082: Claude-Side Consolidated Hook Group Dispatch

## Status

Proposed

## Date

2026-07-16

## Parent

Extends ADR-068 (consolidated per-event hook dispatcher, Copilot CLI). Does
not supersede it. Related: ADR-071 (fail-closed launcher contract), ADR-035
(exit codes; Claude hook semantics remain exempt), ADR-007 (memory-first,
one duplicate enforcer deregistered here), ADR-062 (LSP-first guards, left
as standalone registrations).

## Context

Issue #3075: repository hooks make agent CLIs slow on Windows, where a
Python cold start costs ~250 ms and more under Defender real-time scanning
and machine load. A trusted Copilot CLI 1.0.70 probe measured 71,742 ms
with hooks enabled against 26,994 ms with `disableAllHooks` end to end.

`.claude/settings.json` registered 53 per-hook commands. Per event, Claude
Code spawned one Python process per registration: every Bash call paid 4
PreToolUse spawns plus 1 PostToolUse spawn, every Write/Edit paid 5, every
user prompt 4, every Stop 3, a `git push` 11. Each process independently
spawned `git remote get-url origin` because the consumer-repo cache in
`.claude/lib/hook_utilities/guards.py` is per-process. The installed
project-toolkit plugin registered near-identical hooks, so inside this repo
every event double-fired (observed live: duplicated ADR-007 and Serena
guidance on every prompt).

The 2026-07-14 analysis (`.agents/analysis/2026-07-14-hook-batching-determination.md`)
rejected an earlier ad hoc Claude-side dispatcher because it concatenated
multiple JSON stdout documents, changed blocking-event behavior, replaced
host concurrency silently, invented timeout budgets, lacked generator
ownership, and could recurse after regeneration. It set the bar a safe
multiplexer must meet: one final protocol object, explicit merge rules,
event-correct blocking behavior, sane timeout semantics, and runtime tests
with negative controls.

Distribution context: the project-toolkit plugin is a distribution vehicle
targeting organizational rollout (hundreds of users), not a single-user
convenience. Plugin-surface behavior changes therefore stay membership-
neutral in this ADR; only the publishing repo takes prunes.

## Decision

1. **One process per (event, matcher) group on the Claude side.**
   `.claude/settings.json` and the plugin `hooks.json` register
   `python3 -u .claude/hooks/dispatch_claude.py --group <id>` once per
   group. Membership lives in `.claude/hooks/dispatch_groups.json`.
   `.claude/lib/claude_hook_dispatch.py` runs each member in-process via
   `runpy`, reusing ADR-068's `hook_dispatch.py` helpers (stdin replay,
   exit-code normalization) and citing it as canonical.
2. **Merge rules meet the safe-multiplexer bar.** Per-shim stdout is
   captured and merged into exactly one protocol document: a structured
   decision document (`decision`, `continue`, `permissionDecision`) passes
   through verbatim and alone; context payloads merge into one
   `hookSpecificOutput.additionalContext` for PreToolUse/PostToolUse and
   into joined plain text for UserPromptSubmit, SessionStart, Stop,
   SubagentStop, and PreCompact (where the host injects plain stdout).
3. **Event-correct blocking.** Three modes: `gate` (PreToolUse,
   short-circuit on first non-zero exit or decision document, fail-closed
   on missing shim or exception), `gate_all` (UserPromptSubmit, Stop,
   SubagentStop: every shim runs, first blocking code propagates),
   `observe` (PostToolUse, SessionStart, PreCompact: every shim runs, exit
   is always 0).
4. **No invented timeouts.** Per-shim timeouts are recorded in the manifest
   for generator fidelity; the host enforces the group registration's
   cumulative budget, same division of ownership as ADR-068.
5. **Generator ownership without recursion.** The Copilot generator expands
   dispatcher registrations back to per-hook entries from the same manifest
   (`_expand_dispatch_groups`), so Claude-side consolidation does not alter
   the Copilot tree. The dispatcher never regenerates anything. Parity
   tests pin settings, plugin manifest, dispatch manifest, and disk to each
   other.
6. **Plugin double-fire elimination.** Every plugin hook registration
   routes through the dispatcher; when `CLAUDE_PLUGIN_ROOT`'s plugin name
   equals the project's own published plugin name, the dispatcher exits 0
   immediately (one cheap spawn instead of a duplicated hook set). The
   coverage invariant (plugin shims minus repo-settings shims equals the
   documented prune allowlist) is enforced by
   `tests/hooks/test_dispatch_groups_parity.py`.
7. **Host-side matcher emission for Copilot.** Copilot CLI now honors
   per-entry `matcher` filtering, verified empirically on CLI 1.0.71: a
   PascalCase `PreToolUse` entry with matcher `Bash` fired while `view`,
   `Edit|Write`, and `Bash(git commit*)` entries never spawned. The
   generator emits a tool-name union on a dispatcher entry only when every
   member matcher reduces to documented Claude core tool names
   (`generate_dispatcher.event_matcher_union`); any exotic matcher (MCP
   tool names, the serena regex) fails open to no matcher so no guard can
   silently die on an unmapped runtime name. Command-scoped matchers such
   as `Bash(git commit*)` never match on Copilot and therefore always
   reduce to their tool name; command filtering stays in-process.
8. **Environment pin.** `.claude/settings.json` sets
   `AI_AGENTS_PROJECT_REPO=1` (the documented `guards.py` override), which
   removes the per-process `git remote get-url origin` child spawn inside
   this repository. In-process grouping additionally makes the guards
   module cache shared across a group's members.
9. **Prunes (repo settings only).** `invoke_session_start_memory_first.py`
   is deregistered (duplicate of `invoke_memory_first_enforcer.py` ADR-007
   guidance) and the PostToolUse-Bash `invoke_adr_lifecycle_hook.py`
   registration is dropped (advisory; ADR changes remain gated at commit
   by `invoke_adr_review_guard.py` and on Write/Edit by
   `invoke_adr_architect_gate.py`). Plugin membership is unchanged.

## Measured effect

Per-event spawn counts inside this repo (settings side, before the plugin
dedupe doubles them): Bash 5 to 2, Write/Edit 5 to 2, user prompt 4 to 1,
Stop 3 to 1, git commit 10 to 2, git push 11 to 2, session start 7 to 2.
Linux timing probe for the Bash pre-gate group: 202 ms to 81 ms per call;
the absolute win grows on Windows where the per-spawn cost dominates. The
plugin self-host bail removes the duplicated context injections observed
on every prompt. Copilot-side, the PreToolUse matcher union removes the
dispatcher spawn for `ask_user`, `web_fetch`, and all MCP tool calls.

## Consequences

Negative, accepted:

- Per-shim timeout isolation is lost; a hung shim consumes its group's
  budget (git-push 300 s) and blocks siblings. The old model isolated each
  hook. Accepted as inherent to consolidation; the host still kills the
  group at its budget.
- Sibling shims share `sys.modules`, `sys.path`, and `os.environ`
  mutations within a group (same trade ADR-068 took for Copilot). Shims
  are trusted first-party code.
- Gate mode reports the first block only; the host previously ran hooks
  concurrently and surfaced every denial. Matches ADR-068 gate mode.
- A context-only JSON document's `suppressOutput`/`systemMessage` fields
  are dropped during merge; a `gate_all` shim that blocks and also emits a
  decision document has the document logged to stderr, not merged.
- The self-host bail keys on plugin-name equality. A fork keeping the name
  `project-toolkit` with divergent settings would silently lose plugin
  hooks; the coverage-invariant test protects this repo, not forks.
- Consumers still receive `invoke_session_start_memory_first.py` through
  the plugin (membership frozen here); pruning it for consumers is a
  follow-up plugin change.
- Group membership exists on three surfaces (dispatch manifest, settings,
  plugin manifest); the parity tests are the drift guard.
- Copilot matcher emission assumes matcher-aware CLI versions ignore or
  honor the field; pre-matcher versions that ignored unknown fields fall
  back to the previous fire-always behavior with in-process filtering.

## Rejected alternatives

- Prune-only (the 2026-07-14 recommendation): keeps 4 spawns per Bash call
  and the plugin double-fire; does not meet the issue #3075 goal.
- Generic multiplexer without capture/merge: the previously rejected code
  path; fails the single-JSON-document protocol requirement.
- Registering plugin hooks only and emptying repo settings: contributors
  without the plugin lose every gate; plugin releases lag the repo.

## Evidence

- `.agents/analysis/2026-07-16-adr-082-architect-review.md` (architect
  gate verdict: APPROVE-WITH-CHANGES; conditions resolved in-change).
- 26 dispatcher tests (`tests/hooks/test_claude_hook_dispatch.py`) with
  negative controls, including real-payload runtime contract runs where a
  raw `gh pr view` still exits 2 through the dispatcher.
- 34 parity tests (`tests/hooks/test_dispatch_groups_parity.py`) including
  the self-host coverage invariant.
- Generator expansion tests (`tests/build_scripts/test_dispatch_expansion.py`)
  and matcher-union tests (`tests/build_scripts/test_dispatcher_matcher_union.py`).
- Copilot CLI 1.0.71 matcher probe (isolated `COPILOT_HOME`, user-level
  hooks file, marker files): `bash`-matcher and `Bash`-matcher entries
  fired; `view`, `Edit|Write`, and `Bash(git commit*)` entries never
  spawned. Recorded in session 3044.
