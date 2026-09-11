# Repo Map

Agent-first navigation: what to edit, what is generated, what to skip.
Root `AGENTS.md` owns protocol and gates. `.claude/rules/*.md` owns conventions
(auto-loaded by each file's `paths:` glob). This file owns navigation only.

## Sources of truth (edit here)

| Path | Owns | Regen / gate |
|---|---|---|
| `templates/agents/*.shared.md` | Copilot CLI + VS Code agent bodies (31) | `uv run python build/generate_agents.py` |
| `src/claude/*.md`, `.claude/agents/*.md`, `.github/agents/*.agent.md` | Hand-maintained agent copies; shared edits touch template + all three | `build/scripts/validate_install_parity.py` (co-change only) |
| `.claude/rules/*.md` (29) | Cross-harness conventions, canonical | `generate_rules.py` -> `.github/instructions/`, `src/copilot-cli/instructions/` |
| `.claude/skills/<name>/` (111) | Skills, the only user-invocable surface (ADR-064) | `generate_skills.py` -> `src/copilot-cli/skills/` |
| `.claude/hooks/`, `.claude/settings.json` | Claude Code hooks | `generate_hooks.py` -> `src/copilot-cli/hooks/` |
| `scripts/{hook_utilities,github_core,ai_review_common}` | Plugin lib source | `scripts/sync_plugin_lib.py` -> `.claude/lib/` -> `build_all.py` -> `src/copilot-cli/lib/` (run sync first) |
| `.claude/skills/review/references/<role>.md` | PR quality-gate prompts | `generate_pr_quality_prompts.py` -> `.github/prompts/pr-quality-gate-<role>.md` |
| `.agents/architecture/ADR-*.md` (108) | Decisions; frontmatter `status` is truth | `generate_adr_index.py` -> `.agents/architecture/README.md`; any edit fires `adr-review` |
| `.agents/governance/` | Constraints; `PROJECT-CONSTRAINTS.md` is index of record | ADR + human approval for changes |
| `scripts/` | Automation, Python only (ADR-042) | tests in `tests/` |
| `build/` | Generators, drift and parity gates | `tests/build_scripts/` |
| `lefthook.yml` | Hook wiring; logic in `scripts/validation/git_hook_policy.py <subcmd>` | ADR-006 |
| `.github/workflows/` | CI wiring; logic in `scripts/ci/`, `.github/scripts/` | SHA-pinned actions |

Per-directory agent docs: `build/AGENTS.md`, `scripts/AGENTS.md`, `templates/AGENTS.md`,
`src/AGENTS.md`, `src/claude/AGENTS.md`, `.github/AGENTS.md`, `.agents/AGENTS.md`,
`.claude/skills/CLAUDE.md`.

## Generated (never edit)

`src/copilot-cli/**` | `src/vs-code-agents/**` | `.github/instructions/**` |
`.github/prompts/pr-quality-gate-*.md` | `docs/agent-catalog.md` | `.agents/architecture/README.md`

Regen: `uv run python build/scripts/build_all.py`. Drift gate: `--check` (CI and `pre_pr.py`).
Full inventory: `.agents/governance/GENERATOR-FILES.md`.

## Skip unless the task names it

| Path | Why |
|---|---|
| `.agents/{sessions/*.json,archive,retrospective,critique,analysis,qa,planning,plans,projects,audits,audit,checkpoints,eval-results,metrics,pr-checks,pr-consolidation,incidents,devops,debt,benchmarks,roadmap}` | Historical artifacts; evidence, not instructions |
| `.agents/sessions/handoffs/` | The one live subtree: per-issue continuity (read latest at start, update at end) |
| `.agents/memory/episodes/` (751) | Auto-extracted; searched via memory skill, never read whole |
| `.serena/memories/` (197) | Retrieval aid; `/memory-search` or `uv run python .claude/skills/memory/scripts/search_memory.py "<query>"` |
| `evals/`, `tests/evals/`, `tests/eval_scenarios/` | Eval corpora and reports; runners in `scripts/eval/` |
| `.claude-mem/`, `.factory/`, `.diffray/`, `.codeql/`, `.baseline/`, `.serena/cache/` | Tool state |
| `packages/ai-agents-cli/` (bun, TS), `packages/semantic-hooks/` (own uv project) | Separate toolchains |
| `src/*.ts`, `src/transforms/` | Copilot target emitter; `tests/*.test.ts` run by `cli-smoke.yml` (`bun test`) |
| `*/CLAUDE.md` seven-line `<claude-mem-context>` stubs | Plugin placeholders; edit only outside the tags |
| `README.md`, `CONTRIBUTING.md`, other `docs/*.md` | Human onboarding prose |

## Commands

| Task | Command |
|---|---|
| Tests | `uv run pytest tests/ -x` (120s per-test timeout; skill tests in `tests/skills/<name>/`) |
| Lint | `uv run ruff check .` (line length 100; syntax target py310, runtime 3.14) |
| Pre-PR gate | `uv run python scripts/validation/pre_pr.py` (`--quick` skips slow gates) |
| Regen or drift | `uv run python build/scripts/build_all.py [--check]` |
| Agents only | `uv run python build/generate_agents.py` (`--validate`, `--what-if`) |
| Push | `/push-pr` skill; PRs via `github` skill, never raw `gh` when a skill exists |

## Traps

- Docs: `python3 <tracked>.py` fails the doc-interpreter gate; write `uv run python`.
- Em or en dash anywhere authored fails `staged-dashes` (fixtures under `tests/hooks/fixtures/` exempt).
- More than 5 authored files per commit fails `atomic-commit`; `detect_scope_explosion.py` warns at 10 files, blocks at 50.
- Hook bypass (`--no-verify`, `LEFTHOOK=0`, `LEFTHOOK_EXCLUDE`, ...) is forbidden; hand the branch back with the measurement.
- `git ls-files '*.ps1'` is empty; PowerShell in older docs is history, not guidance.
- Serena writes from a linked worktree land in the activating checkout, not yours.
