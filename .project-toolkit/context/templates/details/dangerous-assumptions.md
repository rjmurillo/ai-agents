## Dangerous assumptions

- `uv run python build/generate_agents.py` alone never populates `copilot_sources` and never writes `src/claude/agents/`: it falls back to `.shared.md` for copilot-cli. No `github` platform file exists, so `.github/agents` is only a link to `src/copilot-cli/agents`.
- Lefthook auto-regen globs `agents/*.shared.md` and `platforms/**` only; a `.tmpl`, partial, rule, skill or hook edit triggers nothing. Run `build_all.py` yourself.
- `$toolset:` never reaches Claude Code: expansion lives in `generate_agents_common.py`, called only by `generate_agents.py`, and no `.claude.md.tmpl` or partial uses it. `analyst` and `security` carry a literal `tools:` list no gate compares against `toolsets.yaml`.
- The `Skill Markdown Portability` ratchet is per file and scans `.md` only, so a repo-internal path added to a skill or rule template raises the count on generated output you cannot edit (`.claude/skills/<name>/SKILL.md`, `src/copilot-cli/instructions/<name>.instructions.md`). `agents/*.shared.md` is scanned; `.tmpl` files and partials are not.
