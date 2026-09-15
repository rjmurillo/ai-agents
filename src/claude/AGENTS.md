# src/claude/

`claude-agents` plugin source in the `rjmurillo/ai-agents` repository. The generated trees below binplace into `.claude/`.

<!-- vendor-portability: repo-only contributor guide; templates/, build/, .github/agents/ and sibling src/ trees do not ship with this plugin -->

## Matters

- Generated (ADR-109 B1 to B4): `agents/` 31, `rules/` 28, `skills/<name>/SKILL.md` 111, `hooks/` plus `hooks.json`.
- Hand-maintained: `claude-instructions.template.md`, `security/references/`, `.claude-plugin/plugin.json`, this file.
- Edit the template, never the render. A hand-edit fails its Template Drift gate next run.
- Agent frontmatter: `name`, `description`, `argument-hint` in all 31. `metadata.role` in 25. `tools:` only `analyst.md`, `security.md`. `model:` only `code-reviewer.md`.
- `skills/<name>/` holds SKILL.md alone, no `scripts/`, `references/`, `tests/`.

## Entry points

- `templates/agents|rules|skills|hooks/` is the edit location; per-class render map in `templates/AGENTS.md`. Generator order, owned prefixes, binplace, gate semantics: `build/AGENTS.md`.

## Where to look

| Path | Why |
|---|---|
| `agents/merge-resolver.md`, `agents/pr-comment-responder.md`, `agents/quality-auditor.md` | Hard-code a plugin-root skills path; see Constraints |

## Skip

- `.claude/agents/`, `.claude/rules/`, `.claude/skills/<name>/SKILL.md`, `.claude/hooks/` minus its seven hand-maintained docs: byte-for-byte binplace copies of this tree.

## Constraints

- Cross-harness change: read `agent-harness-reference` first, route through `ai-agents-portability-campaign`.
- `model:` needs an ADR-080 `KEEP_PIN` sidecar entry, or a bare alias (`sonnet`, `opus`, `haiku`) plus `model-rationale:` priced below the harness default through the platform `model_tiers` map (`check_model_pins.py`). Only `code-reviewer.md` qualifies.
- Those three agents read `${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/<name>/scripts` (`merge-resolver.md` still bare `${CLAUDE_PLUGIN_ROOT:-.claude}`; `plugin-self-containment.md` MUST 2 wants the nested form). Resolves only when `project-toolkit` (`.claude/`) installs alongside `claude-agents`: this tree ships no skill scripts.

## Dangerous assumptions

- A green `detect_agent_drift.py` proves nothing about `src/vs-code-agents/` parity: its code default `--claude-path` is `src/claude`, not `src/claude/agents` (its `--help` claims otherwise), so it compares 0 of 31 agents. The `Agent Drift Detection` gate runs it bare. Pass `--claude-path src/claude/agents`.
- `git add` silences the `src/` staleness gate and proves nothing; commit.

## Dependencies

- Marketplace entry `claude-agents`, `source: ./src/claude`. Nothing above it ships to an installer.

## Architecture

- A render stage, not a source.

## Commands

```bash
uv run python build/scripts/build_all.py                   # regenerate every tree
uv run python build/scripts/build_all.py --check            # drift gate, all four classes
```
