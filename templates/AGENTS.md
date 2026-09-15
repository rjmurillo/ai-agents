# templates/

Canonical source for five ADR-109 artifact classes: agents, rules, skills, hooks, settings; the `prompts` row's source sits outside this tree.

## Matters

Per-class render map. Compilers run inside `build_all.py` except `prompts`; binplace copies the plugin tree onto the install tree byte for byte.

| Class | Source here | Compiler | Plugin tree -> install tree |
|---|---|---|---|
| agents | `agents/<stem>.claude.md.tmpl`, `.copilot.md.tmpl`, `agents/partials/` | `agent_templates.py` | `src/claude/agents/` -> `.claude/agents/` |
| rules | `rules/<name>.md` | `rule_templates.py` | `src/claude/rules/` -> `.claude/rules/` |
| skills | `skills/<name>.SKILL.md.tmpl`, `skills/partials/` | `skill_templates.py` | `src/claude/skills/<name>/SKILL.md` -> `.claude/skills/<name>/SKILL.md` |
| hooks | `hooks/` minus `settings.tmpl`: 13 executables plus 3 data files | `hook_templates.py` | `src/claude/hooks/`, `src/claude/hooks.json` -> `.claude/hooks/` |
| settings | `hooks/settings.tmpl` | `hook_templates.py` | none -> `.claude/settings.json` |
| prompts | `.claude/skills/review/references` | `generate_pr_quality_prompts.py` | none -> `.github/prompts/` |

- `generate_agents.py` renders `src/copilot-cli/agents/`, `src/vs-code-agents/`, and via `platforms/github.yaml` `.github/agents/` (no `model:`; GitHub rejects it, issue #4938).
- `generate_rules.py` mirrors `src/claude/rules/` to `.github/instructions/` and `src/copilot-cli/instructions/`.
- `generate_hooks.py` with `generate_dispatcher.py` reads `src/claude/hooks/` and `hooks.json`, writes `src/copilot-cli/hooks/`, binplaced to `.github/hooks/`.
- `agents/<stem>.shared.md` feeds `src/vs-code-agents/` and `docs/agent-catalog.md`; it is also `generate_agents.py`'s stem list: no `.shared.md`, no copilot-cli, vs-code or github file for that stem.
- A literal `{{` in a rule template is written `\{{`.
- Lib renders from `scripts/` packages, not from here (B5); `.claude-plugin/marketplace.json` stays hand-maintained until B6.

## Entry points

`uv run python build/scripts/build_all.py` renders every class but `prompts` (`generate_pr_quality_prompts.py`, standalone) and binplaces. Binplace has no standalone CLI.

## Where to look

| Path | Why |
|---|---|
| `platforms/*.yaml` | Per-platform output config; only `github.yaml` lacks `model_tiers` |
| `platforms/binplace.yaml` | Copy manifest; source of the `.claude/` write allowlist |
| `README.md` | Predates ADR-109; names retired hand-edit paths |

## Skip

- Generated, never hand-edited (source is `templates/` except `src/claude/lib`, `src/copilot-cli/lib`, `.claude/lib/<pkg>` from `scripts/`, and `src/copilot-cli/skills` non-SKILL.md from `.claude/skills/<name>/`): `src/claude/agents|rules|skills|hooks`, `src/claude/hooks.json`, `src/copilot-cli/agents|instructions|skills|lib|hooks`, `src/vs-code-agents/`, `.claude/agents|rules|hooks`, `.claude/settings.json`, `.github/agents|hooks|instructions`, each `.claude/skills/<name>/SKILL.md`.
- Hand-maintained inside those trees: the seven docs under `.claude/hooks/`, `.github/agents/security/references/`, `.github/agents/pr-comment-responder.prompt.md`, `src/vs-code-agents/copilot-instructions.md`, under `.claude/skills/<name>/`, everything but `SKILL.md` (the `src/copilot-cli/skills` copy of it is generated).

## Constraints

- `validate_templates_schema.py` validates only a `platforms/*.yaml` carrying a top-level `provider:`, skipping `binplace.yaml`. `binplace_manifest.py` validates that one, requiring every `install_tree` under `.claude/` or `.github/` (`BinplaceConfigError`, exit 2).
- Cross-harness hook, event, or generated-Copilot change: read the `agent-harness-reference` skill, route through `ai-agents-portability-campaign`.

## Dangerous assumptions

- `.claude/rules/templates.md` renders from `rules/templates.md` and is stale: MUST-2, SHOULD-3 and MUST NOT-1 still call `src/claude/`, `.claude/agents/` and `.github/agents/` hand-maintained, MUST-4 denies that any agent template defines `name` while all 31 `.claude.md.tmpl` do, MUST-1 omits `hooks/`. Fix at the template.
- `uv run python build/generate_agents.py` alone never populates `copilot_sources` and never writes `src/claude/agents/`: it falls back to `.shared.md` for copilot-cli and github.
- Lefthook auto-regen globs `agents/*.shared.md` and `platforms/**` only; a `.tmpl`, partial, rule, skill or hook edit triggers nothing. Run `build_all.py` yourself.
- `$toolset:` never reaches Claude Code: expansion lives in `generate_agents_common.py`, called only by `generate_agents.py`, and no `.claude.md.tmpl` or partial uses it. `analyst` and `security` carry a literal `tools:` list no gate compares against `toolsets.yaml`.
- The `Skill Markdown Portability` ratchet is per file and scans `.md` only, so a repo-internal path added to a skill or rule template raises the count on generated output you cannot edit (`.claude/skills/<name>/SKILL.md`, `src/copilot-cli/instructions/<name>.instructions.md`). `agents/*.shared.md` is scanned; `.tmpl` files and partials are not.

## Dependencies

- Generator order, `OWNED_PREFIXES`, the binplace step, gate semantics, the lib render: `build/AGENTS.md`.

## Architecture

- `vscode.yaml` and `visual-studio.yaml` both target `src/vs-code-agents`.

## Commands

```bash
uv run python build/scripts/build_all.py                    # render all + binplace
uv run python build/scripts/build_all.py --check            # CI drift gate
uv run python build/scripts/agent_templates.py --validate
uv run python build/scripts/rule_templates.py --validate
uv run python build/scripts/hook_templates.py --validate
uv run python build/scripts/generate_skills.py --validate
uv run python build/scripts/validate_templates_schema.py
uv run python build/generate_agents.py --what-if
```
