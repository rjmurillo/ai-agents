# /

Root map: what to edit, what is generated, what to skip. `AGENTS.md` owns protocol and gates; `.claude/rules/*.md` owns conventions.

## Matters

- Generated trees are overwritten by the next `build/scripts/build_all.py` run; edit the source. Inventory: `.agents/governance/GENERATOR-FILES.md`.
- `templates/` is canonical for agents, rules, skills, hooks, settings; `scripts/` packages for lib (ADR-109 B1 to B5).

## Entry points

- `AGENTS.md`, `CLAUDE.md` (root): protocol, gates, boundaries, Task-tool and `/autoplan` routing. Read first every session.
- `.claude/rules/*.md`: read the ones whose `paths:` glob matches; edit `templates/rules/<name>.md`, never the rendered copy.

## Where to look

| Path | Why |
|---|---|
| `templates/{agents,rules,skills,hooks}/` | Source for all five classes; `settings` from `hooks/settings.tmpl` |
| `scripts/{hook_utilities,github_core,ai_review_common}` | Plugin lib source; rendered by `build_all.py` (`build/AGENTS.md`) |
| `{.agents,.claude,.claude/hooks,.github,build,scripts,src,src/claude,templates,tests}/AGENTS.md`, `.claude/skills/CLAUDE.md`, `.claude-mem/memories/AGENTS.md` | Per-directory guides |
| `docs/{skill-reference,agent-governance,task-classification-guide,when-to-use,orchestrator-routing-algorithm,search-dont-load,SKILL-AUTHORING,agent-metrics}.md` | Agent-facing; no guide owns `docs/` |

## Skip

| Path | Why |
|---|---|
| `src/`, `.claude/{agents,rules,lib,hooks}/`, `.claude/skills/*/SKILL.md`, `.claude/settings.json`, `.github/{instructions,agents,hooks}/`, `docs/agent-catalog.md`, `.project-toolkit/architecture/README.md` | `build_all.py` `OWNED_PREFIXES`; edit the template (`build/AGENTS.md`) |
| `src/*.md`, `src/claude/{AGENTS.md,claude-instructions.template.md,security/references/}`, every `.claude-plugin/plugin.json`, `src/copilot-cli/{THIRD-PARTY-NOTICES.TXT,docs/}`, `.claude/hooks/**/{AGENTS,CLAUDE,README}.md`, `.claude/skills/*/{scripts,references,tests}/` bar `review/scripts/validate_review_marker.py`, `.github/agents/{pr-comment-responder.prompt.md,security/references/}` | Hand-maintained inside those prefixes |
| `.serena/memories/` | Retrieval aid; `/memory-search`, never read whole |
| `.agents/{archive,retrospective,critique,qa,analysis}/`, `.project-toolkit/memory/episodes/` | Evidence. Live: `.project-toolkit/sessions/handoffs/`, latest at start, update at end |
| `evals/`, `tests/eval_scenarios/` | Corpora; runners in `scripts/eval/`. `tests/evals/` is pytest input |
| `.factory/mcp.json`, `.vscode/mcp.json` | `scripts/sync_mcp_config.py --sync-all` output |
| `.github/prompts/pr-quality-gate-*.md` | `build/scripts/generate_pr_quality_prompts.py`; `build_all.py` skips it |
| `packages/` | Separate toolchains, own lockfiles |

## Constraints

- No em or en dash: `git_hook_policy.py` `staged-dashes` blocks the commit, `branch-dashes` the push; `tests/hooks/fixtures/` exempt.
- `atomic-commit` (over 5 authored files) and `scripts/detect_scope_explosion.py` (10 or more on the branch) are advisory, never blocking (ADR-100).
- A documented bare-interpreter call on a tracked script with a non-stdlib import fails `scripts/validation/check_doc_interpreter_portability.py`; baseline empty. Exempt: `tests/`, generated mirrors, 16 `HISTORICAL_ROOTS` (not `.agents/{memory,metrics,roadmap,plans}/`). Use `uv run python <path>`.
- `build/scripts/validate_path_normalization.py --fail-on-violation` scans Markdown for an absolute home or drive path.

## Dangerous assumptions

- "`.claude/` is hand-authored" is false for `.claude/{agents,rules,hooks}/`, `.claude/skills/*/SKILL.md`, `.claude/settings.json` and the `.claude/lib/` packages (split in `.claude/AGENTS.md`); exceptions in the Skip row above.

## Dependencies

- `build_all.py --check` is the drift gate: direct in `validate-generated-agents.yml`, indirect in `agent-drift-detection.yml` via `scripts/ci/check_plugin_lib_mirrors.py`, local via `pre_pr.py` Generated Artifact Staleness.
- No workflow invokes `scripts/validation/pre_pr.py`; `lefthook.yml` runs it pre-push and pre-commit (`--markdown-lint-only`).
- Template-drift and parity gate semantics: `build/AGENTS.md`.

## Architecture

- Per-class render path: `templates/AGENTS.md`.

## Commands

```bash
uv run pytest tests/ -x                       # 120s timeout
uv run ruff check .                           # line length 100, target py310
uv run python scripts/validation/pre_pr.py    # --quick skips slow gates
uv run python build/scripts/build_all.py      # --check for the drift gate
uv run python build/generate_agents.py --validate  # also agent-drift-detection.yml
# Push via /push-pr; PRs via the github skill, never raw gh.
```
