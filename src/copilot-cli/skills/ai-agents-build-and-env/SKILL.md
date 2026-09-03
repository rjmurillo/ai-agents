---
name: ai-agents-build-and-env
version: 1.0.0
description: >-
  Runbook to recreate the ai-agents dev environment from scratch and survive
  its traps, including the uv-pinned Python 3.14.6, git hooks install, MCP
  layer setup, contributor commands, and PEP 668.
  Use when you say `set up this repo`, `bootstrap the environment`, `fresh
  clone setup`, or you hit `ModuleNotFoundError yaml`. Do NOT use for the
  generation pipeline (use `ai-agents-generation-and-release`) or CI gate
  evidence rules (use `ai-agents-validation-and-qa`).
license: MIT
---

# ai-agents Build and Environment Runbook

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->
Recreate a working dev environment for this repository from a fresh clone, verify
it actually works, and avoid the traps that have cost prior contributors real
time. Audience: a zero-context mid-level engineer or Sonnet-class model. Every
command below was verified against the repo on 2026-07-03; the Provenance section
gives a re-verification one-liner for each volatile fact.

## Triggers

- `set up this repo`
- `bootstrap the environment`
- `fresh clone setup`
- `ModuleNotFoundError: No module named yaml`
- `environment traps`

## Scope

This skill is environment setup and survival only. Adjacent problems route to
siblings:

| You want | Use instead |
|----------|-------------|
| Regenerate mirrors, run the drift gates, release | `ai-agents-generation-and-release` |
| Understand what counts as test evidence, run CI-equivalent gates | `ai-agents-validation-and-qa` |
| Full catalog of env vars, skip markers, escape hatches | `ai-agents-config-catalog` |
| Triage a failing hook, gate, or test | `ai-agents-debugging-playbook` |

## Process

### Phase 1: Prerequisites

The interpreter version has ONE source of truth: `.python-version` (currently
`3.14.6`, as of 2026-07-03). Do not hardcode versions anywhere; read the pin.

| Tool | Floor | Verify |
|------|-------|--------|
| uv | Must resolve the `.python-version` pin (old container uv builds cannot; reinstall via the astral.sh standalone installer, never `uv self update`, which hits GitHub API rate limits on shared egress IPs) | `uv python list "$(cat .python-version)"` prints a row |
| Python | Exactly the `.python-version` pin, installed by uv | `python3 --version` |
| Node.js | 22 LTS (`NODE_MAJOR=22` in `scripts/bootstrap-vm.sh:40`; AGENTS.md floor says "Node LTS") | `node --version` |
| PowerShell | 7.5.4+ per AGENTS.md Stack. Note: zero `.ps1` files remain in the repo (ADR-042 Python migration), so pwsh is rarely exercised, but the floor is still declared | `pwsh --version` |
| gh CLI | 2.60+ per AGENTS.md Stack | `gh --version` |
| git, jq, curl | any recent | `git --version` |

Container or VM setup: `bash scripts/bootstrap-vm.sh` automates all of the above
on Ubuntu (needs sudo; export `GH_TOKEN` first). It installs uv, the pinned
Python via `uv python install --default`, Node 22, pwsh, gh, syncs dependencies,
and installs Lefthook. Do not copy its shell implementation for new scripts;
ADR-042 requires Python for new automation.

Manual Python install when not using the bootstrap script:

```bash
uv python install --default "$(cat .python-version)"
```

### Phase 2: Core Install

From the repo root:

```bash
uv sync --frozen --extra dev
uv run --frozen lefthook install --reset-hooks-path
uv run --frozen lefthook check-install
```

What these do:

- `uv sync --frozen --extra dev` builds `.venv/` from `uv.lock` exactly as
  locked (`--frozen` never rewrites the lockfile) with dev extras. The pre-push
  gate runs validation through `uv run --frozen`, so this `.venv` is the
  environment a push validates against (`scripts/bootstrap-vm.sh:109-115`).
- `lefthook install` installs Git shims for the events in `lefthook.yml`.
  `check-install` verifies that the shims are active. Lefthook reads the
  configuration at runtime, so editing the jobs under an already-installed hook
  type needs no reinstall. Adding or removing a hook type does: with
  `no_auto_install: true` set, the new type has no shim until install runs
  again.

### Phase 3: Verify the Install

Run each; expected output shown. If any differs, stop and fix before working.

```bash
uv run --frozen lefthook version
# expect: 2.1.10

uv run --frozen lefthook check-install
# expect: exit 0

uv run pytest tests/test_paths.py --collect-only -q
# expect: "28 tests collected" (count as of 2026-07-03)

uv run python -c "import yaml; print(yaml.__version__)"
# expect: 6.0.3 (PyYAML pin in pyproject.toml project.dependencies)
```

### Phase 4: MCP Layer

`.mcp.json` at repo root defines three servers. Copy `.env.example` to `.env`
and fill keys (`ANTHROPIC_API_KEY`, `PERPLEXITY_API_KEY`, `TAVILY_API_KEY`,
`CONTEXT7_API_KEY`, `YDC_API_KEY`; optional `COMPRESS_TOKENIZER`). Never commit
`.env` (universal.md MUST 5: no secrets).

| Server | Transport | Role | When absent |
|--------|-----------|------|-------------|
| serena | stdio, `uvx --from git+https://github.com/oraios/serena` (port 24282, context claude-code) | Canonical memory (ADR-007) plus LSP symbol navigation | Memories stay readable as plain files under `.serena/memories/` (122 files as of 2026-07-03). The LSP read gate that could misfire on code files was retired in #3216 |
| forgetful | stdio, `uvx forgetful-ai` | Supplementary semantic memory search | ADR-007 fallback: use the Serena `memory-index` memory for keyword discovery. MUST NOT block work or skip memory retrieval because Forgetful is down (ADR-007 "Graceful degradation") |
| deepwiki | http, `https://mcp.deepwiki.com/mcp` | External GitHub repo documentation | No local impact; fall back to web search |

Proxy and TLS note (generic, not environment-specific): the two stdio servers
are fetched by `uvx` on first launch, so a corporate proxy must allow uv's
downloads and uv must trust the proxy CA. Use standard `HTTPS_PROXY` plus uv's
system-certificate option (`UV_SYSTEM_CERTS`; the older `UV_NATIVE_TLS` name is
deprecated as of uv 0.11.26). Never disable TLS verification.

### Phase 5: Editor and LSP Reality

This repo prefers LSP-first navigation (ADR-062, `.claude/rules/lsp-first.md`):
use Serena symbol tools over grep for code navigation. This is static steering
now, not a runtime gate. The PreToolUse LSP gate and its environment escapes
(`SKIP_LSP_GATE`, `LSP_GATE_MODE`, `LSP_DOWN`) were retired in #3216; no Read
call is blocked and there is nothing to set.

## Known Traps

Each row verified 2026-07-03. Longer stories live with the sibling skills
`ai-agents-failure-archaeology` and `ai-agents-debugging-playbook`.

| Trap | Symptom | Fix |
|------|---------|-----|
| CONTRIBUTING.md build commands were DEAD before PR #2871 | `CONTRIBUTING.md:155` said `build/Generate-Agents.ps1` PowerShell invocation until PR #2871 repointed it to `build/generate_agents.py`; zero `.ps1` files exist in the repo (ADR-042) | Real commands: `uv run python build/generate_agents.py` and `uv run python build/scripts/build_all.py` |
| PEP 668: bare pip fails | `pip install X` errors with externally-managed-environment on uv-managed interpreters | Everything goes through uv: `uv sync`, `uv add`, `uv run` (`scripts/bootstrap-vm.sh:118-123`) |
| Skill scripts need the project venv | `.claude/skills/github/scripts/pr/*.py` import `github_core`, which imports `yaml` at load; bare `python3` throws `ModuleNotFoundError: No module named 'yaml'` unless `.venv/bin` is first on PATH (bootstrap-vm.sh arranges that; a manual setup usually does not) | Run skill scripts with `uv run python`, which resolves the venv deterministically |
| Moving a worktree leaves the uv shebangs stale | Direct `.venv/bin/pytest` fails with "bad interpreter" after `mv`; the shebangs in `.venv/bin/*` (POSIX) or `.venv/Scripts/*` (Windows) still name the old worktree path (issue #3170) | Run `scripts/maintenance/repair_worktree_venv.py` with `uv run python` (or `uv sync --frozen --extra dev --reinstall`: `--reinstall` recreates the launchers a bare `--frozen` sync would leave stale, `--extra dev` keeps pytest/ruff/mypy, `--frozen` matches CI); prefer `uv run python -m pytest` for move-safe validation |
| Two floors, not one | `pyproject.toml project.requires-python` says `requires-python = ">=3.14"` (the dev/install contract), but plugin hooks run under the host's ambient interpreter, which may be older | Develop and test against `.python-version` (3.14.6). The blocking CI syntax gate parses every file at the hook-portability floor (3.10), NOT 3.14, so hooks stay portable to older hosts (issue #2655, decoupled from `requires-python` in issue #3008); see `ai-agents-debugging-playbook` |
| LF line endings enforced | CRLF in YAML frontmatter breaks the Copilot CLI parser (github/copilot-cli#694); `.gitattributes:59` sets `* text=auto eol=lf` | Configure your editor for LF; never commit CRLF |
| Pre-push jobs can take minutes | Lefthook runs the named validators in `lefthook.yml` for matching push files | Budget minutes per push; do not attempt `--no-verify` (prohibited, AGENTS.md Never list) |
| Skill test locations differ | New tests belong in `tests/skills/NAME/`; legacy suites remain under `.claude/skills/NAME/tests/` | The default suite reaches legacy suites through `tests/test_skill_bundle_suites_run.py`. Invoke a legacy path directly only for targeted diagnosis; details in `ai-agents-validation-and-qa` |

## Verification

The 15-minute smoke checklist. All boxes checked means the environment works.

- [ ] `uv run --frozen lefthook version` prints `2.1.10`
- [ ] `uv run --frozen lefthook check-install` exits 0
- [ ] `uv run python -c "import yaml"` exits silently (venv has project deps)
- [ ] `uv run pytest tests/test_paths.py -q` passes (28 passed, under 1 second, as of 2026-07-03)
- [ ] `uv run ruff --version` prints a version (0.15.16 as of 2026-07-03)
- [ ] `python3 --version` matches `cat .python-version`
- [ ] `node --version` prints v22.x, `gh --version` prints 2.60+, `pwsh --version` prints 7.5+
- [ ] `.env` exists locally (copied from `.env.example`) and is NOT tracked: `git ls-files .env` prints nothing
- [ ] Optional, requires network: Serena and Forgetful MCP servers start (harness lists `mcp__serena__*` tools); if not, confirm the ADR-007 fallbacks in Phase 4 before proceeding

## Anti-Patterns

- Following CONTRIBUTING.md or templates/README.md build instructions. They
  predate ADR-042; the pwsh commands cannot run.
- `pip install` anything, or `uv pip install` into the interpreter. PEP 668
  blocks it; the venv from `uv sync --frozen --extra dev` is the environment.
- Pushing with `--no-verify` or recreating a skip flag for the pre-push hook.
  Escape hatches here get teeth or get abused (session 1187); skipping hooks is
  on the AGENTS.md Never list.
- Committing `.env`, or putting keys anywhere but env vars (universal.md MUST 5).
- Editing files with a CRLF editor profile. One CRLF save can break Copilot CLI
  YAML frontmatter parsing downstream.
- Treating a missing MCP server as a blocker. ADR-007 mandates graceful
  degradation: fall back per the Phase 4 table and keep working.
- Hand-fixing `.venv` contents or relying on whatever system `python3` happens
  to resolve to. Re-run `uv sync --frozen --extra dev` instead.

## Provenance and Maintenance

Authored 2026-07-03. All commands in this file were executed read-only against
the repo on that date. Re-verify volatile facts before trusting them:

| Fact | Source | Re-verify |
|------|--------|-----------|
| Python pin 3.14.6 | `.python-version` | `cat .python-version` |
| `requires-python >=3.14` install floor | `pyproject.toml project.requires-python` | `grep -n requires-python pyproject.toml` |
| Syntax-gate hook floor 3.10 (separate from install floor) | `scripts/validation/validate_python_syntax.py` `_SUPPORT_FLOOR` | `grep -n _SUPPORT_FLOOR scripts/validation/validate_python_syntax.py` |
| PyYAML 6.0.3 pin | `pyproject.toml project.dependencies` | `grep -n PyYAML pyproject.toml` |
| `uv sync --frozen --extra dev` is the canonical sync | `scripts/bootstrap-vm.sh:114` | `grep -n "uv sync --frozen" scripts/bootstrap-vm.sh` |
| Node 22 LTS | `scripts/bootstrap-vm.sh:40` | `grep -n NODE_MAJOR scripts/bootstrap-vm.sh` |
| pwsh 7.5.4+, gh 2.60+ floors | AGENTS.md Stack section | `grep -n "gh 2.60" AGENTS.md` |
| Zero .ps1 files (ADR-042) | repo tree | `git ls-files "*.ps1"` prints nothing |
| Stale pwsh commands | `CONTRIBUTING.md:155,741` | `grep -n pwsh CONTRIBUTING.md` |
| Git hook jobs, filters, and validators | `lefthook.yml` | `uv run --frozen lefthook validate` |
| MCP servers serena/deepwiki/forgetful | `.mcp.json` | `cat .mcp.json` |
| .env key names | `.env.example` | `cat .env.example` |
| Forgetful fallback table | `ADR-007` (`.agents/architecture/ADR-007-memory-first-architecture.md:108-130`) | `grep -n "Graceful degradation" .agents/architecture/ADR-007-memory-first-architecture.md` |
| LF enforcement rationale | `.gitattributes:59` and header comments | `grep -n "eol=lf" .gitattributes` |
| Serena memory file count (122) | `.serena/memories/` | `python3 -c "from pathlib import Path; print(sum(1 for _ in Path('.serena/memories').iterdir()))"` |
| tests/test_paths.py count (28) | pytest | `uv run pytest tests/test_paths.py --collect-only -q` |
| uv TLS var rename | uv 0.11.26 runtime warning | `uv run python -c pass` under `UV_NATIVE_TLS` |

Maintenance rule: if any re-verify command disagrees with this file, the repo
won. Update this skill in the same PR that changes the underlying fact. Do not
touch `.claude-plugin/plugin.json`: the manifests carry no version (ADR-092, see
`ai-agents-change-control`).
