# .claude/

Plugin root shipping as `project-toolkit`; `hooks/` and `skills/` have own guides.

## Matters

- Generated, never hand-edit: `agents/`, `rules/`, `skills/<name>/SKILL.md`, `hooks/`, `settings.json`, `lib/` packages plus `lib/bootstrap.py`. Sources are `templates/` files and the repo's `scripts/` packages in the `rjmurillo/ai-agents` repository.
- Hand-maintained here: `lib/` (mixed, see next line), `CLAUDE.md`, this guide, `.claude-plugin/plugin.json`, the seven doc files under `hooks/`, each skill's non-`SKILL.md` files.
- `lib/` mixed: `ai_review_common/`, `github_core/`, `hook_utilities/`, `bootstrap.py` are binplaced renders of `scripts/` packages, never hand-edit; the top-level modules (`claude_hook_dispatch.py`, `paths.py`, siblings) have no `scripts/` source and are edited here.

## Entry points

- New rule: `templates/rules/<name>.md` with `paths:` frontmatter; a literal `{{` is written `\{{`. Needs an activation scenario or its id in the pre-PR `Rule Activation Coverage` baseline. Language-universal scope is budget-gated, not blocked: pre-PR `Instruction Budget (always-on)`.
- Three always-on rules, each `paths: ["**"]` plus `priority: critical`: `rules/universal.md`, `builder-ethos.md`, `voice.md`. Editing one, or adding a fourth, moves figures `skills/context-optimizer/references/model-context-doctrine.md` states in prose; pre-PR `Always-on Corpus Claims` pins those to live measurement: update that doc in the same change.
- `settings.json` renders from `templates/hooks/settings.tmpl`, no plugin-tree hop: `hooks` wires four session-boundary events for this checkout (`SessionStart`, `UserPromptSubmit`, `SessionEnd`, `PreCompact`); `permissions`, `env`, `enabledPlugins` are separate top-level keys; `enabledPlugins` pins `project-toolkit@ai-agents` to `false` (JSON `false` only) so this checkout does not load its own plugin twice.

## Where to look

| Path | Why |
|---|---|
| `rules/*.md` | Rendered copy binplaced by `build_all.py`; `generate_rules.py` mirrors the plugin tree, not this copy, to two instruction trees |
| `CLAUDE.md` | Passive every session, 4,000-token budget; edit outside `<claude-mem-context>` |
| `.claude-plugin/plugin.json` | Manifest: name, description, author only |

## Skip

- `.gitignore`: excludes `settings.local.json`, `*.local.*` only.

## Constraints

- Every `.md` under `agents/` needs a non-empty `description:`; the loader registers any file there as a subagent regardless. Pre-PR `Agent Tree Frontmatter (.claude/agents)` fails on a miss, no allowlist. Fix the template, never here.
- Adding a per-call event (`PreToolUse`, `PostToolUse`, `PermissionRequest`, `PostToolUseFailure`): clear every MUST in `tool-use-hook-bar.md` (auto-loads for `settings.json`). The four session-boundary entries are outside it.

## Dangerous assumptions

- "`rules/`, `agents/`, `skills/<name>/SKILL.md`, `hooks/`, `settings.json`, `lib/` packages are hand-authored" is false since ADR-109 B1 to B5; `generated-artifacts.md` auto-loads for all but `settings.json`.
- "A hook wired in `settings.json` ships to plugin consumers" is false; see `.claude/hooks/AGENTS.md`.
- "This guide loads like `CLAUDE.md`" is false: on demand, never passively budgeted.

## Dependencies

- `lib/` packages and `bootstrap.py` arrive by binplace from the repo build, one command, no separate sync step (ADR-109 B5); a hand edit here reds pre-PR `Generated Artifact Staleness`.

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
