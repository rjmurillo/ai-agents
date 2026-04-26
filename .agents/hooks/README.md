# `.agents/hooks/` — Harness-Agnostic Hook Contract

This directory defines the **harness-agnostic contract** for deterministic
quality gates on ai-agents. It is the portable layer consumed by
Claude Code, Copilot CLI, and any other agent harness that can exec
a shell command, read stdin as JSON, and honor an exit code.

> Scope note: This is the Phase 1 contract drop for issue #1726.
> The canonical in-repo implementation today lives under `.claude/hooks/`
> (Claude Code). Additional harnesses (Copilot CLI, etc.) consume the same
> contract through `hooks.yaml` and the reference scripts in `examples/`.

## Why Hooks (Not Prompts)

Prompt-based compliance has a documented 95.8% failure rate after context
compaction. Hooks execute outside the model, so the model cannot forget,
skip, or rationalize them away. Every gate below is enforceable by the
harness layer regardless of model state.

See `.agents/retrospective/2026-01-09-session-protocol-violation-analysis.md`.

## The `exit 2` Convention

All hooks in this contract follow a single exit-code semantic shared with
Claude Code and Copilot CLI:

| Exit | Meaning                                          |
|-----:|--------------------------------------------------|
| `0`  | Allow. Tool use continues normally.              |
| `2`  | Block. Tool use is denied; message goes to user. |
| any other | Treated as an infrastructure error; fail open with a warning on stderr. |

This is deliberately coarser than ADR-035's general exit code taxonomy. Hook
scripts are **exempt from ADR-035** because the harness only distinguishes
"allow" from "block." Everything else routes to a logged warning so that a
broken hook never silently blocks work.

## Hook Events

The contract defines five events. Each maps 1:1 to Claude Code's and
Copilot CLI's lifecycle events so existing harness hooks satisfy the contract
without rewrites.

| Event          | Fires                                    | Purpose                                                |
|----------------|------------------------------------------|--------------------------------------------------------|
| `SessionStart` | A new agent session begins               | Auto-load context (CLAUDE.md, AGENTS.md, HANDOFF.md)   |
| `PreToolUse`   | Before any tool call                     | Verify preconditions; block on violation               |
| `PostToolUse`  | After any tool call                      | Persist state and side-effects                         |
| `Stop`         | Session ends (done, crash, or timeout)   | Generate handoff and retrospective                     |
| `PreCompact`   | Context window nears the harness limit   | Checkpoint state before compaction destroys it         |

A harness that lacks one event MAY satisfy the contract by emulating it
from adjacent events (e.g., `PreCompact` may be approximated via a
periodic `PostToolUse` watermark).

## Contract Manifest: `hooks.yaml`

The declarative manifest `hooks.yaml` is the source of truth for which
checks apply to which event. Each entry names a script, an event, and an
optional tool or path matcher. Harness adapters read this file and register
the scripts in whatever format the harness requires.

See `hooks.yaml` in this directory for the current manifest.

## Reference Implementations

The `examples/` directory contains portable shell implementations for
harnesses without a native hook ecosystem. They are the minimum-viable
proof that the contract is usable; production deployments should point
at the harness-native implementations in `.claude/hooks/` instead.

## Mapping to Existing Implementations

| Contract Event | Claude Code path                  | Status                                 |
|----------------|------------------------------------|----------------------------------------|
| `SessionStart` | `.claude/hooks/SessionStart/`     | Implemented (memory-first enforcer, session init) |
| `PreToolUse`   | `.claude/hooks/PreToolUse/`       | Implemented (11 gates: session log, branch, security, ADR, etc.) |
| `PostToolUse`  | `.claude/hooks/PostToolUse/`      | Implemented (markdown lint, CodeQL, observation sync) |
| `Stop`         | `.claude/hooks/Stop/`             | Implemented (session validator, skill learning)    |
| `PreCompact`   | (not yet wired)                    | Deferred; see follow-up                            |

## Acceptance Criteria Coverage (Issue #1726)

This is a Phase 1 delivery. It establishes the contract and the mapping;
it does not rewrite the existing hooks or add new measurement.

- [x] Hook directory structure defined at `.agents/hooks/`
- [x] Documentation of the hook architecture and `exit 2` convention
      (this file plus `hooks.yaml`)
- [x] Hooks work with at least one harness (Claude Code, via the mapping
      table above and the manifest in `hooks.yaml`)
- [x] `SessionStart`, `PreToolUse`, and `Stop` hooks satisfied by the
      existing `.claude/hooks/` implementation
- [ ] Dedicated ADR for hook architecture — **deferred**. The ADR write
      path is gated by the architect review hook; a separate PR will land
      the ADR with the required multi-agent debate artifacts.
- [ ] Measurable >80% compliance improvement — **deferred**. Requires
      multi-session telemetry outside this PR's scope.

## Follow-Up Work

- ADR-058 (or next available number): formalize the hook architecture
  with architect debate, as required by the adr-review skill.
- `PreCompact` hook implementation for checkpoint-before-compaction.
- Copilot CLI adapter that reads `hooks.yaml` and registers scripts
  against the 26 Copilot lifecycle events.
- Compliance telemetry so the 95.8% → >80% acceptance criterion can be
  measured against a baseline.
