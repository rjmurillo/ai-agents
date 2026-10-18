## Matters

Per-class render map. Compilers run inside `build_all.py` except `prompts`; binplace copies the plugin tree onto the install tree, or symlinks it (`link: true`: `agents`, `skills`, `rules`; ADR-119).

| Class | Source here | Compiler | Plugin tree -> install tree |
|---|---|---|---|
| agents | `agents/<stem>.claude.md.tmpl`, `.copilot.md.tmpl`, `agents/partials/` | `agent_templates.py` | `src/claude/agents/` -> `.claude/agents/` |
| rules | `rules/<name>.md` | `rule_templates.py` | `src/claude/rules/` -> `.claude/rules/` (link; repo-only: real) |
| skills | `skills/<name>.SKILL.md.tmpl`, `skills/partials/` | `skill_templates.py` | `src/claude/skills/<name>/` -> `.claude/skills/<name>` (link) |
| hooks | `hooks/` minus `settings.tmpl`: 14 executables plus 2 data files | `hook_templates.py` | `src/claude/hooks/`, `src/claude/hooks.json` -> `.claude/hooks/` |
| settings | `hooks/settings.tmpl` | `hook_templates.py` | none -> `.claude/settings.json` |
| prompts | `.claude/skills/review/references` | `generate_pr_quality_prompts.py` | none -> `.github/prompts/` |

- `generate_agents.py` renders `src/copilot-cli/agents/`, `src/vs-code-agents/`; `.github/agents/*.agent.md` link to the former (inherit-only, no `model:`).
- `generate_rules.py` mirrors `src/claude/rules/` to `src/copilot-cli/instructions/` (linked into `.github/instructions/`).
- `generate_hooks.py` with `generate_dispatcher.py` reads `src/claude/hooks/` and `hooks.json`, writes `src/copilot-cli/hooks/`, binplaced to `.github/hooks/`.
- `agents/<stem>.shared.md` feeds `src/vs-code-agents/` and `docs/agent-catalog.md`; it is also `generate_agents.py`'s stem list: no `.shared.md`, no copilot-cli, vs-code or github file for that stem.
- A literal `{{` in a rule template is written `\{{`.
- Lib renders from `scripts/` packages, not from here (B5); `.claude-plugin/marketplace.json` stays hand-maintained (one Claude entry, `project-toolkit` at `./src/claude`, since B6).
