# templates/

Source of truth for every rendered agent tree (Claude Code, Copilot CLI, GitHub, VS Code/Visual Studio) and the ADR-108 skill-template class.

## Matters

- Agent sources per stem: `.claude.md.tmpl`, `.copilot.md.tmpl`, `.shared.md` (31 each), `agents/partials/*.mustache` (138).
- All three per-stem files are required. `generate_agents.py`'s stem list is `agents/*.shared.md` (`build/generate_agents.py:325`), so a stem with no `.shared.md` yields no `src/copilot-cli/agents/`, `src/vs-code-agents/` or `.github/agents/` file at all; `agent_templates.discover()` rejects a stem carrying only one of the `.tmpl` pair.
- `agent_templates.py` renders `src/claude/agents/`, binplaced to `.claude/agents/`; `generate_agents.py` renders `src/copilot-cli/agents/`, `src/vs-code-agents/`, and (`platforms/github.yaml`, no `model:`, issue #4938) `.github/agents/`.
- `.shared.md` alone feeds `src/vs-code-agents/` (Dangerous assumptions covers the copilot-cli/github fallback).
- All five agent output trees are generated per stem; no `<stem>` agent file in any of them is hand-maintained (non-agent files: Skip).
- `skills/*.SKILL.md.tmpl` + `skills/partials/*.mustache` (23 + 13, ADR-108) compile to `.claude/skills/<name>/SKILL.md` via `build_all.py`, not `generate_agents.py`.
- `tools` / `tools_vscode` / `tools_copilot` MUST stay block-style YAML lists; an inline array breaks Copilot CLI on CRLF (issue #893).

## Entry points

- `agents/<stem>.claude.md.tmpl`, `<stem>.copilot.md.tmpl`: Claude Code / Copilot CLI+GitHub behavior.
- `agents/<stem>.shared.md`: VS Code/Visual Studio behavior.
- `toolsets.yaml`, `platforms/*.yaml`: tool groups; per-platform output config.
- `uv run python build/scripts/build_all.py`: regenerates everything; the only path to `.claude/agents/` (binplace has no standalone CLI).

## Where to look

| Path | Why |
|---|---|
| `agents/<stem>.claude.md.tmpl`, `<stem>.copilot.md.tmpl`, `<stem>.shared.md` | Per-platform sources (ADR-109 B1): `.tmpl` pair compiled by `agent_templates.py`; `.shared.md` feeds VS Code/Visual Studio plus the copilot-cli/github fallback |
| `platforms/copilot-cli.yaml`, `github.yaml`, `vscode.yaml`, `visual-studio.yaml` | `includeNameField: true` for the first two, `false` for the last two; only `github.yaml` has no `model_tiers` (GitHub rejects `model:`); `toolsFrom` sets the tool vocabulary: `github.yaml` to `copilot-cli` (`tools_copilot`), `visual-studio.yaml` to `vscode` |
| `platforms/binplace.yaml` | Copy manifest, no `provider:` key: `agents` row copies `src/claude/agents` to `.claude/agents`, `skills` row (`plugin_tree: null`, `compile: skill_templates`) targets `.claude/skills`; both rows feed the `.claude/` write allowlist |
| `toolsets.yaml` | Named `$toolset:<name>` groups; Copilot CLI, GitHub and VS Code output only (see Dangerous assumptions) |
| `README.md` | ADR-036 procedure still runs; ADR-052 is target state, not implemented. Predates ADR-109 B1 throughout (zero ADR-109 mentions): `:131` and `:137` send you to hand-edit `src/claude/{agent}.md`, a retired path and a retired practice; `:126` and `:181` assert the retired separately-maintained model |
| `.claude/rules/templates.md` | Binding MUST/SHOULD/MUST NOT; MUST-1, 2, 4, MUST NOT-1 and SHOULD-3 are stale, see Dangerous assumptions |

## Skip

- `src/claude/agents/`, `.claude/agents/`, `.github/agents/`, `src/copilot-cli/agents/`, `src/vs-code-agents/`: the 31 per-stem agent files in each are generated. Edit the source, regenerate. The other tracked files there have no template and are hand-maintained: `.github/agents/security/references/*.md`, `.github/agents/pr-comment-responder.prompt.md`, `src/vs-code-agents/copilot-instructions.md`.
- `.claude/skills/<name>/SKILL.md` for a template-owned skill: generated from its `.tmpl`.

## Constraints

- Regenerate, commit output, toolset integrity, frontmatter, and the `model_tier`/ADR-080 pin rule: `templates.md` MUST-1 through 5 (1, 2 and 4 are stale, see Dangerous assumptions; 3 and 5 bind).
- `agents/*.shared.md` sits in the `Skill Markdown Portability` ratchet (`check_skill_md_portability.py` `EXTRA_SCAN_ROOTS`; baseline `scripts/validation/skill_md_portability_baseline.json`, 14 entries here): a new repo-internal path reference raises that file's count and fails pre-PR. It scans `.md` only, so the `.tmpl` pair and `partials/*.mustache` are outside it even though their text ships in `src/copilot-cli/agents/`.
- `platforms/*.yaml` schema: `validate_templates_schema.py` (`safe_load`, no anchors, `schemaVersion` semver check, path traversal rejection). It validates only files with a top-level `provider:` (or legacy `platform:`), so `binplace.yaml` skips that gate; `binplace_manifest.py` validates it instead (same `load_platform_config`, plus per-row relative-path, containment and symlink checks, and `install_tree` MUST be under `.claude/` or `.github/`), raising `BinplaceConfigError` as exit 2.
- Cross-harness hook, event, or generated-Copilot change: read the `agent-harness-reference` skill, route through `ai-agents-portability-campaign`.

## Dangerous assumptions

- `.claude/rules/templates.md` predates ADR-109 B1 throughout, not only its preamble: MUST-2 and MUST NOT-1 repeat the hand-maintained claim, MUST NOT-1 sends you to hand-edit `src/claude/<agent>.md` (retired path, retired practice), MUST-4 says no agent template defines `name` while all 31 `.claude.md.tmpl` do, and MUST-1's `generate_agents.py` is the insufficient command below. MUST-3 and MUST-5 still bind. SHOULD-3 says 18 sections (`SECTIONS_TO_COMPARE` is 23), still says "hand-maintained copies", and prescribes a bare `python3` invocation.
- `validate_install_parity.py`'s agent check is retired and cannot fail (`build/AGENTS.md`); `build_all.py --check` catches a `src/claude/agents/`-only edit missing its template.
- `detect_agent_drift.py` never reads template bodies, so a green `Agent Drift Detection` row (skipped by `--quick`) is no evidence a template edit landed; it also runs with no `--claude-path`, so its blocking pair compares 0 of 31 agents (`src/claude/AGENTS.md`). The gates that do catch a template edit are `Agent Template Drift` (`agent_templates.py --validate`, byte-for-byte vs `src/claude/agents/`) and `Skill Template Drift` (`generate_skills.py --validate`).
- `uv run python build/generate_agents.py` alone never populates `copilot_sources` (no CLI flag); it skips `src/claude/agents/`, falling back to `.shared.md` for copilot-cli/github instead of the compiled `.copilot.md.tmpl`.
- Lefthook auto-regen globs `agents/*.shared.md` and `platforms/**` only (`lefthook.yml:276-304`, blocking: the job returns `generate_agents.py`'s exit code): a `.claude.md.tmpl`, `.copilot.md.tmpl` or partial edit triggers nothing. Run `build_all.py` yourself.
- `$toolset:` never reaches Claude Code: expansion lives in `generate_agents_common.py`, called only by `generate_agents.py`. 28 of 31 `.shared.md` and `.copilot.md.tmpl` use it; zero `.claude.md.tmpl` and zero partials do. A `toolsets.yaml` edit moves Copilot CLI, GitHub and VS Code output only; the two `.claude.md.tmpl` that need tools (`analyst`, `security`) carry a literal `tools:` list you edit by hand, the other 29 declare none, and no gate compares either against `toolsets.yaml`.
- `model_tier` reaches only the Copilot/VS Code/Visual Studio mirrors. No `.claude.md.tmpl` has one; `code-reviewer.claude.md.tmpl:4` pins Claude Code with a literal `model: haiku` plus `model-rationale:`, rendered verbatim by `agent_templates.py`. `check_model_pins.py` scans `*.shared.md` and the rendered trees, never `*.claude.md.tmpl`, so a bad pin here is reported against files you must not edit.
- `build/sync_slim_agents.py` targets this tree: `--write` copies bodies from the now-generated `src/claude/agents/` over `agents/<stem>.shared.md` and `.github/agents/` for its 9 `SLIMMED_AGENTS`. Today it writes nothing: 7 of its 18 declared files carry wording its transforms cannot reproduce, so `--write` refuses the whole run and exits 2 (`--check` prints the blocked lines). No gate runs it; reconciling those lines re-arms a backwards copy over ADR-109 output.

## Dependencies

- Feeds `generate_agents.py` + `agent_templates.py` in `build_all.py`'s `agents` step, then `agent-catalog` (`agents/*.shared.md` -> `docs/agent-catalog.md`), then a `binplace` step; full generator order and the `.claude/` write allowlist: `build/AGENTS.md`.
- CI (`validate-generated-agents.yml`): `generate_agents.py --validate`, then `build_all.py --check`, then an install-parity step. `agent-drift-detection.yml` (PR-gating, `[skip-drift-check]` bypass) and weekly `drift-detection.yml` (Mondays 09:00 UTC, audit only) are separate workflows.

## Architecture

- One generated seam covers every agent tree (Matters); no manual seam remains.
- `vscode.yaml` and `visual-studio.yaml` both target `src/vs-code-agents`; no separate Visual Studio output directory.

## Commands

```bash
uv run python build/scripts/build_all.py                   # regenerate everything + binplace
uv run python build/scripts/build_all.py --check            # CI drift gate (OWNED_PREFIXES)
uv run python build/generate_agents.py                      # copilot-cli/agents, vs-code-agents, .github/agents
uv run python build/generate_agents.py --validate            # regenerate + diff, no write
uv run python build/generate_agents.py --what-if             # dry run
uv run python build/scripts/agent_templates.py --validate    # check src/claude/agents vs templates
uv run python build/scripts/validate_templates_schema.py     # schema-check platforms/*.yaml
uv run python build/scripts/detect_agent_drift.py --all --claude-path src/claude/agents  # 80% floor; the default --claude-path is src/claude and compares 0 of 31
uv run python build/scripts/generate_skills.py --validate     # check SKILL.md.tmpl output (ADR-108)
```
