# /

Repo root map: what an agent edits, what is generated, and what to skip before touching any file in ai-agents. Root `AGENTS.md` owns protocol and gates; `.claude/rules/*.md` owns conventions (auto-loaded per each file's `paths:` glob). This file owns navigation only.

## Matters

- Generated trees are silently overwritten by the next `build/scripts/build_all.py` run; edit the source tree, never the output. Full source-to-output map: `.agents/governance/GENERATOR-FILES.md`.
- `.claude/skills/<name>/` is the only user-invocable surface (ADR-064); `.claude/commands/` is retired and `scripts/validation/check_commands_retired.py` blocks a command file reappearing under any plugin root.
- Every per-directory `AGENTS.md` below is hand-maintained, not generated: a shared-behavior edit needs the template plus every sibling copy changed together.
- `src/claude/` looks like a generated mirror and is not one: no generator writes it, and `build/scripts/validate_install_parity.py` blocklists `AGENTS.md`/`CLAUDE.md` from every parity group, so that tree has no automated drift gate.
- `.agents/architecture/ADR-*.md` frontmatter `status` is the truth, not the filename or the index; editing any ADR file fires the `adr-review` skill.

## Entry points

- `AGENTS.md` (root): protocol, gates, boundaries. Read first every session.
- `CLAUDE.md` (root): imports `AGENTS.md`, adds Claude Code Task-tool routing and `/autoplan` skill routing.
- `.claude/rules/*.md`: read the ones whose `paths:` frontmatter glob matches the file before editing it.
- `scripts/validation/pre_pr.py`: pre-PR gate; run before every push.
- `build/scripts/build_all.py`: regenerates every generated tree; `--check` is the CI drift gate.

## Where to look

| Path | Why |
|---|---|
| `templates/agents/*.shared.md` (31) | Canonical source for Copilot CLI + VS Code agent bodies |
| `src/claude/*.md`, `.claude/agents/*.md`, `.github/agents/*.agent.md` | Hand-maintained agent copies; edit template + all three together |
| `.claude/rules/*.md` (29) | Cross-harness conventions, canonical source |
| `.claude/skills/<name>/` (111) | Skills; only user-invocable surface (ADR-064) |
| `.claude/hooks/`, `.claude/settings.json` | Claude Code hook source |
| `scripts/{hook_utilities,github_core,ai_review_common}` | Plugin lib source; sync before regen |
| `.claude/skills/review/references/<role>.md` | PR quality-gate prompt source |
| `.agents/architecture/ADR-*.md` (108) | Decisions of record; `status` frontmatter is truth |
| `.agents/governance/` | Constraints; `PROJECT-CONSTRAINTS.md` is index of record |
| `scripts/` | Automation, Python only (ADR-042); tests in `tests/` |
| `build/` | Generators plus drift/parity gates; tests in `tests/build_scripts/` |
| `lefthook.yml` | Hook wiring only; logic in `scripts/validation/git_hook_policy.py` |
| `.github/workflows/` | CI wiring only; logic in `scripts/ci/`, `.github/scripts/` |
| `build/AGENTS.md`, `scripts/AGENTS.md`, `templates/AGENTS.md`, `src/AGENTS.md`, `src/claude/AGENTS.md`, `.github/AGENTS.md`, `.agents/AGENTS.md`, `.claude/skills/CLAUDE.md` | Per-directory agent docs; read before editing that tree |

## Skip

| Path | Why |
|---|---|
| `.agents/{sessions/*.json,archive,retrospective,critique,analysis,qa,planning,plans,projects,audits,audit,checkpoints,eval-results,metrics,pr-checks,pr-consolidation,incidents,devops,debt,benchmarks,roadmap}` | Historical artifacts; evidence, not instructions |
| `.agents/sessions/handoffs/` | The one live subtree here: per-issue continuity, read latest at start, update at end |
| `.agents/memory/episodes/` (750 tracked JSON) | Auto-extracted; search via the `memory` skill, never read whole |
| `.serena/memories/` (1037 tracked `.md`; `.obsidian/` is editor config, not a memory) | Retrieval aid; use `/memory-search` or `uv run python .claude/skills/memory/scripts/search_memory.py "<query>"` |
| `evals/`, `tests/evals/`, `tests/eval_scenarios/` | Eval corpora and reports; runners live in `scripts/eval/` |
| `.claude-mem/`, `.factory/`, `.diffray/`, `.codeql/`, `.baseline/`, `.serena/cache/` | Tool state, not source |
| `packages/ai-agents-cli/` (bun, TypeScript), `packages/semantic-hooks/` (own uv project) | Separate toolchains, own lockfiles |
| `src/*.ts`, `src/transforms/` | Copilot target emitter; `tests/*.test.ts` run by `.github/workflows/cli-smoke.yml` via `bun test` |
| Any `*/CLAUDE.md` that is only a seven-line `<claude-mem-context>` stub | Plugin placeholder; edit only outside the tags |
| `README.md`, `CONTRIBUTING.md`, other `docs/*.md` | Human onboarding prose, not agent-facing |

## Constraints

- No em or en dash in authored text; `staged-dashes` (`scripts/validation/git_hook_policy.py staged-dashes`) blocks the commit. `tests/hooks/fixtures/` is exempt.
- More than 5 authored files in one commit fails `atomic-commit` (`scripts/validation/git_hook_policy.py atomic-commit`); `scripts/detect_scope_explosion.py` warns at 10 files and blocks a push over 50.
- A documented `python3 <tracked>.py` invocation fails the doc-interpreter-portability gate (`scripts/validation/check_doc_interpreter_portability.py`); the fixed form is `uv run python <path>`.
- Hook bypass is forbidden outright: `--no-verify`, `LEFTHOOK=0`, an overridden `LEFTHOOK_BIN`, a lefthook config override, a direct edit to an installed hook, or `LEFTHOOK_EXCLUDE` (`.claude/rules/universal.md` MUST NOT 2).
- New GitHub Actions references must pin to a commit SHA, never a floating tag (`.claude/rules/universal.md` MUST 8).
- Worktrees must be external: a sibling of the checkout or `~/worktrees/`, never under the clone or a system temp directory (`.claude/rules/universal.md` MUST 6).

## Dangerous assumptions

- "`src/claude/` is a generated mirror, so I don't need to hand-edit it" is false: no generator writes it, and the parity validator excludes `AGENTS.md`/`CLAUDE.md` from every group, so this tree had no drift gate at all until the gap was named.
- "PowerShell docs mean a `.ps1` script exists somewhere" is false: `git ls-files '*.ps1'` returns zero tracked files; PowerShell mentions in older docs are history, not a live target.
- "A green local test run clears a red remote check" is false unless the checker, ruleset, flags, and version are demonstrably identical (`.claude/rules/universal.md` MUST 4).
- "Serena memory writes always land where I'm sitting" is false from a linked worktree: the write resolves through the checkout that activated the Serena project, not the worktree's own directory, and still reports success.
- "This map's file counts are a contract" is false: they are a freshness signal. `.agents/memory/episodes/` and `.serena/memories/` grow every session; re-verify with `git ls-files` before citing a count elsewhere.

## Dependencies

- `build/scripts/build_all.py` reads every "Where to look" source tree and writes every generated path in "Skip"; `--check` is the drift gate run by `.github/workflows/agent-drift-detection.yml` and `.github/workflows/validate-generated-agents.yml`, and the same local checks are wired through `lefthook.yml` into `scripts/validation/git_hook_policy.py` subcommands, re-run in CI by `.github/workflows/pr-validation.yml` via `scripts/validation/pre_pr.py`.
- `scripts/sync_plugin_lib.py` must run before `build_all.py` when `scripts/{hook_utilities,github_core,ai_review_common}` changes, or `.claude/lib/` and its `src/copilot-cli/lib/` mirror go stale.
- Any `.agents/architecture/ADR-*.md` edit feeds the `adr-review` skill (multi-agent debate) and `build/scripts/generate_adr_index.py` (regenerates `.agents/architecture/README.md`).

## Architecture

- Asymmetric generation seam: most trees generate one-way, source to output, but `src/claude/*.md`, `.claude/agents/*.md`, `.github/agents/*.agent.md` are three hand-maintained copies of the same template, kept equal by a co-change validator (`build/scripts/validate_install_parity.py`), not by generation.
- Plugin lib is a four-step chain, order matters: `scripts/{hook_utilities,github_core,ai_review_common}` (source) then `scripts/sync_plugin_lib.py` then `.claude/lib/` then `build/scripts/build_all.py` then `src/copilot-cli/lib/`. Hooks generate through two cooperating generators instead, `build/scripts/generate_hooks.py` plus `build/scripts/generate_dispatcher.py`, both reading `.claude/hooks/` and `.claude/settings.json` and both writing into `src/copilot-cli/hooks/`.

## Commands

| Task | Command |
|---|---|
| Tests | `uv run pytest tests/ -x` (120s per-test timeout; skill tests in `tests/skills/<name>/`) |
| Lint | `uv run ruff check .` (line length 100; syntax target py310, runtime 3.14) |
| Pre-PR gate | `uv run python scripts/validation/pre_pr.py` (`--quick` skips slow gates) |
| Regen or drift | `uv run python build/scripts/build_all.py` (add `--check` for the drift gate) |
| Agents only | `uv run python build/generate_agents.py` (`--validate`, `--what-if`) |
| Push | `/push-pr` skill; PRs and comments via the `github` skill, never raw `gh` when a skill exists |
