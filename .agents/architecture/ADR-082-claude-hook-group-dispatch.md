---
id: ADR-082
status: accepted
date: 2026-07-16
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
---

# ADR-082: Claude-Side Consolidated Hook Group Dispatch

## Status

Accepted on 2026-07-20 after the mandatory six-role review reached six Accept
votes. Review history lives in `.agents/critique/ADR-082-debate-log.md`.

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
   `.claude/settings.json` and the plugin `hooks.json` contain
   `python3 -u .claude/hooks/invoke_dispatch_claude.py --group <id>` once per
   group. Membership lives in `.claude/hooks/dispatch_groups.json`.
   `.claude/lib/claude_hook_dispatch.py` runs each member in-process via
   `runpy`, reusing ADR-068's `hook_dispatch.py` helpers (stdin replay,
   exit-code normalization, process-level stdout capture) and citing it as
   canonical. The entry point validates the manifest before running a shim:
   the event and mode must be a reviewed pair, the shim list must be nonempty,
   and each case-insensitively unique `.py` path must remain relative to the
   hooks directory and resolve to a unique target. Malformed groups,
   path-resolution failures, path escapes, and unexpected entry-point execution
   errors exit 2.
2. **Merge rules meet the safe-multiplexer bar.** Per-shim stdout is
   captured across Python streams, direct writes to file descriptor 1, and
   inherited child processes, then merged into exactly one protocol document.
   Only an event-valid blocking document may terminate a group: top-level
   `continue: false`; top-level `decision: block` with a string reason for
   Stop or SubagentStop; or nested PreToolUse
   `hookSpecificOutput.permissionDecision: deny` with a string reason.
   Optional common fields must also have valid types. A validated blocker
   passes through verbatim and alone. Malformed object-shaped JSON,
   allow-shaped decisions, unsupported decision fields, and invalid field
   types fail closed in gate modes. Observe mode suppresses those invalid
   objects. Context payloads merge into one
   `hookSpecificOutput.additionalContext` for PreToolUse/PostToolUse and
   into joined plain text for UserPromptSubmit, SessionStart, Stop,
   SubagentStop, and PreCompact (where the host injects plain stdout).
   A JSON object with no recognized protocol keys is context, not a terminal
   decision. The dispatcher warns and continues so an advisory or debug object
   cannot skip a later gate.
3. **Event-correct blocking.** Three modes: `gate` (PreToolUse,
   short-circuit on exit 2 or a validated blocking document, continue after
   other nonzero hook errors, fail-closed on missing shim, invalid structured
   output, or exception), `gate_all` (UserPromptSubmit, Stop, SubagentStop:
   every shim runs; exit 2 or invalid structured output blocks, while a
   validated blocking document is emitted at exit 0),
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
   other. Generated Copilot entrypoints require case-insensitively unique
   `.py` basenames and reject drive-relative or separator-bearing paths.
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
   registration is dropped (advisory; ADR changes were historically gated at
   commit by the deleted `invoke_adr_review_guard.py` and on Write/Edit by
   the deleted `invoke_adr_architect_gate.py`). Plugin membership is unchanged.
   **Amended 2026-07-26 (Issue #3399):** both named hooks have since been
   deleted. The parenthetical recorded why the prune was safe at the time
   and is left standing as the decision's rationale, but a reader looking
   for today's enforcement point should go to the lefthook `adr-review-policy`
   job, which runs `scripts/validation/git_hook_policy.py adr-review` over
   the staged set. The prune itself is unaffected: the registration it
   dropped is still dropped.
10. **Group ids are opaque.** A group id is a dispatcher lookup key. It
    carries no contract with the shims the group holds, the matcher it uses,
    the event it serves, or the order of anything. Nothing may make semantic
    assertions on its content. The decision is recorded because the silence reads as an
    invitation: a group-name coherence gate (an id should name the hooks it
    holds) was proposed while closing #3349 and looks like an obvious
    invariant. Replayed across the last 14 revisions of
    `.claude/hooks/dispatch_groups.json` it fired on healthy groups in 12 of
    them. `pretooluse-write-edit` names its matcher rather than its shims and
    is correct; `plugin-posttooluse-1-markdown_auto_lint` matched only
    because the group held one shim, and would have broken the moment a second
    joined. That group is historical: issue #5154 (2026-08-18) deleted it
    under ADR-085 section 10, so read it here as a worked example, not as a
    live group. A rule clean against exactly one tree is tuned to that tree, not
    to an invariant. The falsification is in PR #3372 and the #3349 discourse.
    Membership, event, and mode are the contract, and the manifest already
    states all three; naming is a convenience for humans reading the file.

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
- Sibling shims share `sys.modules`, `os.environ`, and other process-global
  mutations within a group. The runner restores `sys.argv` and `sys.path`
  around every shim, but it cannot undo imported-module or environment state.
  Shims are trusted first-party code.
- Gate mode reports the first block only; the host previously ran hooks
  concurrently and surfaced every denial. Matches ADR-068 gate mode.
- An exit-2 gate shim keeps its pre-grouping compatibility contract: raw stdout
  is forwarded verbatim and the block ends the group. Other nonzero exits are
  Claude hook errors, so later gates still run. The first such error propagates
  only when no later exit-2 or validated blocking document supersedes it.
- When that nonblocking error survives, Claude ignores the group's merged
  stdout. Context from successful later siblings is therefore not delivered,
  unlike direct registrations. The error still reaches stderr and remains
  visible as a hook failure.
- A standalone `{"systemMessage": ...}` document (the LSP guards' warn
  path) merges as context and never terminates a gate group; a
  `suppressOutput` flag riding on a context-only document is dropped
  during merge. A `gate_all` shim that blocks and also emits a decision
  document has the document logged to stderr, not merged. JSON with no
  recognized protocol keys becomes context with a stderr warning, and later
  gates still run.
- The self-host bail keys on plugin-name equality. Any project can copy that
  identity and suppress the installed plugin dispatcher. This is a performance
  dedupe, not a security boundary: project hook configuration is trusted code
  that can already execute arbitrary commands. The coverage-invariant test
  protects this publishing repo, not consumers or forks.
- Consumers previously received `invoke_session_start_memory_first.py` through
  the plugin. That consumer prune is completed; the hook and plugin membership
  are gone.
- Group membership exists on three surfaces (dispatch manifest, settings,
  plugin manifest); the parity tests are the drift guard.
- Copilot matcher emission assumes matcher-aware CLI versions ignore or
  honor the field; pre-matcher versions that ignored unknown fields fall
  back to the previous fire-always behavior with in-process filtering.

## Reversibility and Rollback

This decision owns no persistent data. Rollback restores direct Claude hook
registrations from the event, matcher, timeout, status message, and member
records already stored in `.claude/hooks/dispatch_groups.json`. Replace each
dispatcher command in `.claude/settings.json` and `.claude/hooks/hooks.json`
with those member commands, then run the parity, hook runtime, and generator
tests. Keep the source hooks and manifest until the direct registrations pass.

Rollback restores per-hook process and timeout isolation, repeated Python
startup, and host-owned concurrent execution. It also removes the self-host
dedupe, so the publishing repo must avoid installing its own plugin or accept
duplicate hook execution. The Copilot generator already expands the same group
records to direct generated entries, which proves the manifest retains enough
information for this reversal.

## Re-evaluation Triggers

Reopen this decision when Claude changes hook stdout, exit-code, matcher, or
timeout behavior; a grouped shim adds a new structured output shape; a group
adds an untrusted producer; a process-state mutation affects a sibling; or
measured grouped latency no longer beats direct registration on Windows and
Linux. Any new terminal output shape requires positive, negative, edge, and
later-gate bypass tests before use.

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
- Dispatcher tests (`tests/hooks/test_claude_hook_dispatch.py`) with negative
  controls for unknown JSON, malformed or allow-shaped decisions, empty or
  malformed groups, event/mode mismatch, duplicate and unsafe paths,
  path-resolution failure, process-state isolation, and a real-payload runtime
  run where a branch-mismatched forced push exits 2 through the dispatcher.
- Hook and generator contract command:
  `uv run pytest -q tests/hooks/test_claude_hook_dispatch.py
  tests/hooks/test_dispatch_groups_parity.py tests/test_hook_dispatch.py
  tests/build_scripts/test_generate_dispatcher.py
  tests/build_scripts/test_generate_hooks.py
  tests/build_scripts/test_generate_hooks_injection.py
  tests/build_scripts/test_generate_hooks_runtime_contract.py
  tests/build_scripts/test_copilot_dispatcher_artifact.py
  tests/build_scripts/test_dispatch_expansion.py
  tests/build_scripts/test_dispatcher_matcher_union.py
  tests/build_scripts/test_hook_contract_knowledge.py`.
  Result on 2026-07-20 after Round 6 remediation: 771 passed,
  1 skipped.
- 34 parity tests (`tests/hooks/test_dispatch_groups_parity.py`) including
  the self-host coverage invariant.
- Generator expansion tests (`tests/build_scripts/test_dispatch_expansion.py`)
  and matcher-union tests (`tests/build_scripts/test_dispatcher_matcher_union.py`).
- Copilot CLI 1.0.71 matcher probe (isolated `COPILOT_HOME`, user-level
  hooks file, marker files): `bash`-matcher and `Bash`-matcher entries
  fired; `view`, `Edit|Write`, and `Bash(git commit*)` entries never
  spawned. Recorded in session 3044.
