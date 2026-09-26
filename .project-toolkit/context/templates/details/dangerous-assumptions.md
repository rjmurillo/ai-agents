## Dangerous assumptions

- `.claude/rules/templates.md` renders from `rules/templates.md` and is stale: MUST-2, SHOULD-3 and MUST NOT-1 still call `src/claude/`, `.claude/agents/` and `.github/agents/` hand-maintained, MUST-4 denies that any agent template defines `name` while all 31 `.claude.md.tmpl` do, MUST-1 omits `hooks/`. Fix at the template.
- `uv run python build/generate_agents.py` alone never populates `copilot_sources` and never writes `src/claude/agents/`: it falls back to `.shared.md` for copilot-cli and github.
- Lefthook auto-regen globs `agents/*.shared.md` and `platforms/**` only; a `.tmpl`, partial, rule, skill or hook edit triggers nothing. Run `build_all.py` yourself.
- `$toolset:` never reaches Claude Code: expansion lives in `generate_agents_common.py`, called only by `generate_agents.py`, and no `.claude.md.tmpl` or partial uses it. `analyst` and `security` carry a literal `tools:` list no gate compares against `toolsets.yaml`.
- The `Skill Markdown Portability` ratchet is per file and scans `.md` only, so a repo-internal path added to a skill or rule template raises the count on generated output you cannot edit (`.claude/skills/<name>/SKILL.md`, `src/copilot-cli/instructions/<name>.instructions.md`). `agents/*.shared.md` is scanned; `.tmpl` files and partials are not.
