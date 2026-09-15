# .claude/

Plugin root shipping as `project-toolkit`. Covers `rules/`, `lib/`, `agents/`, `CLAUDE.md`, `settings.json`; `hooks/` and `skills/` have own guides.

## Matters

- `rules/*.md` hand-authored, canonical; `generate_rules.py` mirrors it into two generated instruction trees outside this directory.
- `agents/` generated, never hand-edit. `lib/` mixed: three package subdirs plus `bootstrap.py` synced, never hand-edit; nine top-level modules canonical here, mirrored outward.

## Entry points

- New rule: `rules/<name>.md` with `paths:` frontmatter; regenerate both mirrors same change, outside this directory. Needs an activation scenario or its id in the coverage baseline, also outside: pre-PR `Rule Activation Coverage` is a zero-slack ratchet, fails a rule with neither. Language-universal scope is budget-gated, not blocked: pre-PR `Instruction Budget (always-on)` caps always-on bytes per language; `.py` headroom 6,730 bytes.
- Four always-on rules, each `paths: ["**"]` plus `priority: critical`: `rules/universal.md`, `builder-ethos.md`, `search-before-building.md`, `voice.md`. Editing one, or adding a fifth, moves figures `skills/context-optimizer/references/model-context-doctrine.md` states in prose; pre-PR `Always-on Corpus Claims` pins those to live measurement: update that doc in the same change.
- `settings.json`: `hooks` wires four session-boundary events for this checkout (`SessionStart`, `UserPromptSubmit`, `SessionEnd`, `PreCompact`); `permissions` and `env` are separate top-level keys; `enabledPlugins` pins `project-toolkit@ai-agents` to `false` (JSON `false` only) so this checkout does not load its own plugin twice.

## Where to look

| Path | Why |
|---|---|
| `rules/*.md` | Canonical conventions; `paths:` frontmatter scopes each |
| `agents/*.md` | Dispatchable subagents; generated |
| `CLAUDE.md` | Passive every session, 4,000-token budget; edit outside `<claude-mem-context>` |
| `.claude-plugin/plugin.json` | Manifest: name, description, author only |

## Skip

- `.gitignore`: excludes `settings.local.json`, `*.local.*` only.

## Constraints

- Every `.md` under `agents/` needs a non-empty `description:`; the loader registers any file there as a subagent regardless. Pre-PR `Agent Tree Frontmatter (.claude/agents)` fails on a miss, no allowlist. Fix outside this directory, never here.
- Adding a per-call event (`PreToolUse`, `PostToolUse`, `PermissionRequest`, `PostToolUseFailure`) to `settings.json`: clear every MUST in `tool-use-hook-bar.md` (auto-loads for `settings.json`). The four session-boundary entries are outside it.

## Dangerous assumptions

- "`agents/` is hand-maintained" is false: binplace output since ADR-109 B1; see `claude-agents.md` (auto-loads for `agents/**`).
- "A hook wired in `settings.json` ships to plugin consumers" is false; see `.claude/hooks/AGENTS.md`.
- "This guide loads like `CLAUDE.md`" is false: on demand, never passively budgeted.

## Dependencies

- `lib/` sync chain is two scripts outside this directory; wrong order exits 0 on both, and pre-PR `Generated Artifact Staleness` signals the stale mirror.

## Architecture

- `lib/` is both origin and waypoint.

## Commands

Repository-only, from the `rjmurillo/ai-agents` root, not shipped:

```bash
# paths: only, never applyTo:/globs:/alwaysApply:.
uv run python scripts/validation/check_rule_scope_keys.py
uv run python scripts/validation/check_agent_tree_frontmatter.py
uv run python scripts/validation/pre_pr.py
```
