---
name: ai-agents-config-catalog
description: Catalog of every configuration axis in this repo, env vars, commit markers, frontmatter keys, QA skip verdicts, and escape hatches, each with its enforcement point and abuse story, plus the checklist for adding a new flag safely. Use when you say `what does SKIP_LSP_GATE do`, `list escape hatches`, `can I skip this gate`, `add a config flag`. Do NOT use for hook runtime behavior (use `agent-harness-reference`) or change gating policy (use `ai-agents-change-control`).
version: 1.0.0
license: MIT
---

# AI Agents Config Catalog

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->
Every flag, marker, and skip semantic in this repo, verified against code as of 2026-07-03. Each escape hatch exists because a gate sometimes misfires; each one also has an abuse story or a guard. Before you set any of these, read its row. The house rule (learned in session 1187, see the Removed Flags section): escape hatches get teeth or get abused.

Related skills: `ai-agents-change-control` owns when a bypass is allowed; `agent-harness-reference` and `ai-agents-architecture-contract` own what the hooks themselves do; `ai-agents-debugging-playbook` owns triaging a gate that fired on you.

## Triggers

- `what does SKIP_LSP_GATE do`
- `list escape hatches`
- `can I skip this gate`
- `add a config flag`
- `is this skip marker allowed`

## Process

1. Identify the axis type: env var, commit marker, text directive, frontmatter key, file, or verdict string.
2. Find its row in the tables below. Read the effect AND the guard/abuse column before using it.
3. If you are about to use an escape hatch, confirm the legitimate trigger condition holds (for example, LSP actually down, workflow actually unrunnable under act). Bypassing because a gate is slow or annoying is the session 1187 failure mode.
4. Re-verify the flag still exists with the one-liner in Provenance. Stale docs happen here (CONTRIBUTING.md still documents two removed pre-push flags).
5. Adding a new flag? Follow the checklist in "How to Add a New Flag" and add a row plus a re-verify one-liner to this catalog.

## Environment Variables: LSP Gate (ADR-062)

The LSP gate blocks Read/Grep/Glob on symbol-capable files until Serena warmup plus 2 navigation calls (`NAV_REQUIRED = 2`, `.claude/hooks/PreToolUse/invoke_lsp_read_guard.py:46`). Three escapes with distinct semantics; do not substitute one for another.

| Name | Type | Effect | Status | Guard / abuse story | Where defined |
|---|---|---|---|---|---|
| `SKIP_LSP_GATE=true` | env var | Kill switch: bypasses ALL LSP guards for the process | Production escape hatch | Whole-session blunt instrument; prefer `LSP_DOWN` when the runtime is merely down | `.claude/hooks/PreToolUse/invoke_lsp_read_guard.py:126` |
| `LSP_GATE_MODE=warn` | env var | Downgrades would-be blocks (exit 2) to advisory warnings (exit 0) | Production | Gate still evaluates and prints guidance; nothing is silently allowed | `.claude/hooks/PreToolUse/invoke_lsp_read_guard.py:127,192,273` |
| `LSP_DOWN=true` | env var | Graceful degradation: guards ALLOW native tools with a one-time warning while the language server cannot serve queries | Production | Pure env read, no live probe (ADR-062 Section 8); truthy = case-insensitive `true`/`1`/`yes`/`on` (`lsp_health.py:60` `_TRUTHY`; the nearby comment omits `on`, stale); distinct from the kill switch, relaxes only while LSP is down (issue #2622 per `.claude/rules/lsp-first.md`) | `scripts/hook_utilities/lsp_health.py:57-73` |
| merge/rebase auto-bypass | automatic (not a flag) | Read gate self-bypasses when `MERGE_HEAD`, `rebase-merge`, or `rebase-apply` exists in the git admin dir, or the file's leading window has conflict markers (issue #2454) | Production | No action needed during conflict resolution; do not set the kill switch for merges | `scripts/hook_utilities/lsp_gate_state.py:301,349-350` |

`scripts/hook_utilities/lsp_health.py` is canonical; `.claude/lib/hook_utilities/` is its generated mirror via `scripts/sync_plugin_lib.py`. Never edit the mirror.

## Environment Variables: Git Hooks (.githooks/)

All are scoped, single-check bypasses. Every bypass is printed to the hook output (WARN or SKIP line), never silent.

| Name | Type | Effect | Status | Guard / abuse story | Where defined |
|---|---|---|---|---|---|
| `SKIP_AUTOFIX=1` | env var | pre-commit checks only, does not auto-fix (CI mode) | Production | Check still runs; only the fixer is disabled | `.githooks/pre-commit:18,134` |
| `SKIP_ACTIONLINT=1` | env var | Skips actionlint validation | Emergency only | Bypass is announced in output | `.githooks/pre-commit:477-479` |
| `SKIP_YAMLLINT=1` | env var | Skips yamllint validation | Emergency only | Bypass is announced in output | `.githooks/pre-commit:578-580` |
| `SKIP_MEMORY_SYNC=1` | env var | Skips the memory sync step in pre-commit | Production | Sync is advisory; skipping delays memory freshness only | `.githooks/pre-commit:1784-1792` |
| `SKIP_SCOPE_CHECK=1` | env var | Skips `scripts/detect_scope_explosion.py` cumulative-file scope gate in pre-commit | Escape hatch for justified large sets (generated-artifact bundles, approved oversized-PR repairs) | Prints a WARN naming the flag, not silent (issue #3142); only the literal `1` bypasses, any other value runs the detector; bypassing for convenience or a slow check is the abuse | `.githooks/pre-commit:2137,2163-2167` |
| `SKIP_WORKFLOW_LOCAL_TEST=true` | env var | Bypasses local `act` run of changed workflows in pre-push | Escape hatch for workflows that cannot run under act | Recorded as WARN in the pre-push summary, not silent | `.githooks/pre-push:775-787` |
| `SKIP_CLI_E2E=true` | env var | Opts out of hook-anchoring and plugin-load e2e smoke when a CLI is installed but unusable (unauthenticated, out of credits) | Escape hatch | Recorded as SKIP with named reason | `.githooks/pre-push:1223-1257` |

## Removed and Stale Flags (do not use, do not reintroduce)

| Name | Status as of 2026-07-03 | Story |
|---|---|---|
| `SKIP_PREPUSH` | REMOVED. Zero hits in `.githooks/pre-push`. Still documented at `CONTRIBUTING.md:555` (stale doc, flag on contact) | Abused 3x within hours of creation (session 1187, retro `.agents/retrospective/2026-02-08-session-1187-skip-prepush-abuse.md`). The pre-push hook is now deliberately un-skippable as a whole; only scoped per-check escapes remain |
| `SKIP_TESTS` | Documented at `CONTRIBUTING.md:556` but absent from `.githooks/pre-push` | Same stale doc block as `SKIP_PREPUSH` |

Lesson encoded: a global bypass with no teeth (no telemetry, no approval step) will be reached for under pressure. New escape hatches must be narrow, announced in output, and observable.

## Environment Variables: Tests and Tooling

| Name | Type | Effect | Status | Guard / abuse story | Where defined |
|---|---|---|---|---|---|
| `GIT_CONFIG_COUNT` + `GIT_CONFIG_KEY_0`/`GIT_CONFIG_VALUE_0` | env vars (set by conftest) | Test session injects `commit.gpgsign=false` with command-line precedence so test repos never invoke the user's signing setup | Production test infra | Only sets index 0 when `GIT_CONFIG_COUNT` is unset, so an outer process's config is not clobbered | `tests/conftest.py:35-38` |
| PEP 668 / uv | environment reality | Bare `pip` fails (externally managed env). Everything goes through `uv sync --frozen --extra dev`; skill scripts need `uv run python`, not `python3` (PyYAML lives in the venv) | Production | `ModuleNotFoundError: No module named 'yaml'` means you used the wrong interpreter | `pyproject.toml`, `.python-version` (3.14.6) |
| pytest markers `unit`, `integration`, `security`, `smoke` | pytest -m selectors | Filter test classes; `smoke` = real-CLI tests needing auth/credits, nightly only, and the smoke gate asserts they were NOT skipped (issue #2231 item 4) | Production | Marking a test `smoke` to dodge CI is detected by the not-skipped assertion | `pyproject.toml:46-51` |

## .env Keys (from .env.example)

Copy `.env.example` to `.env`. Keys as of 2026-07-03: `ANTHROPIC_API_KEY` (MCP servers, skill-learning hook LLM fallback, exact token counts), `PERPLEXITY_API_KEY`, `TAVILY_API_KEY`, `CONTEXT7_API_KEY`, `YDC_API_KEY`, and optional `COMPRESS_TOKENIZER` (tiktoken/anthropic/heuristic, default tiktoken). Everything degrades gracefully when absent per ADR-007; missing keys disable the corresponding MCP or fallback path, they do not break the repo. Note: `COMPRESS_TOKENIZER` appears only in `.env.example`; a code consumer was not located in this audit, treat as possibly vestigial.

## Commit Markers

| Name | Type | Effect | Status | Guard / abuse story | Where defined |
|---|---|---|---|---|---|
| `[skip-drift-check]` | commit message marker | Skips the agent drift detection CI gate for the whole PR (marker in ANY commit subject/body counts) | Production escape hatch with obligations | The bypass job posts a checklist that a human must satisfy: reason documented in PR description, `templates/README.md` updated with the intentional difference, explicit code-owner approval. Marker alone is NOT approval | `.github/workflows/agent-drift-detection.yml:65-69` (detection), `:297-320` (obligations); `CONTRIBUTING.md:499` |

## Text Directives (orphan-ref-validator)

| Name | Type | Effect | Status | Guard / abuse story | Where defined |
|---|---|---|---|---|---|
| `orphan-ref-ignore` HTML comment | line directive | Mutes orphan-reference findings for that one line | Production | Rare in tree, easy to grep; compensating control is human review of any commit adding one (DESIGN-009) | `.claude/skills/orphan-ref-validator/scripts/patterns.py:95` |
| `orphan-ref-ignore-file` HTML comment | file directive | Mutes the whole file, but ONLY if the directive appears within the first 50 lines | Production | The 50-line rule prevents burying the mute at the bottom of a long doc | `patterns.py:96`; 50-line window at `scan.py:157` |

Write the directives as HTML comments (`<!-- ... -->`); shown bare here so this catalog does not mute itself.

## Frontmatter Keys (skills)

| Name | Type | Effect | Status | Guard / abuse story | Where defined |
|---|---|---|---|---|---|
| `size-exception: true` | SKILL.md frontmatter | Exempts the file from the 500-line block in the size validator | Escape hatch, must be justified | `taste-lints` only honors it in the first 20 lines of the file; validator prints "size-exception declared" so reviewers see it | `scripts/validation/skill_size.py:107,251`; `.claude/skills/taste-lints/scripts/taste_lints.py:449` |
| `allowed-tools`, `argument-hint` | frontmatter keys | Harness metadata; recognized (not flagged as prose refs) by the orphan-ref scanner | Production | Whitelist lives in one place | `.claude/skills/orphan-ref-validator/scripts/filters.py:31` |

## QA Skip Verdicts (ADR-034)

Session-end QA can be skipped only with one of these exact verdict strings in the session log, and only when the staged files qualify.

| Verdict | When legitimate | Enforcement |
|---|---|---|
| `SKIPPED: investigation-only` | Every staged file matches the allowlist: `.agents/sessions/`, `.agents/analysis/`, `.agents/retrospective/`, `.serena/memories/`, `.agents/security/`, `.agents/memory/` (incl. `episodes/`), `.agents/architecture/REVIEW-*`, `.agents/critique/` | Single source of truth `scripts/modules/investigation_allowlist.py`; pre-check via the `session` skill (Test-InvestigationEligibility); CI backstop `.github/scripts/validate_investigation_claims.py` (advisory) |
| `SKIPPED: docs-only` | All changes are markdown and strictly editorial: spelling, grammar, formatting; no code, config, tests, workflows, or code-block changes | `SESSION-PROTOCOL.md:754`; `CONTRIBUTING.md:694` |

Mixed sessions do not qualify; split the commit. Claiming investigation-only with a code file staged is exactly what the CI backstop exists to catch.

## Plugin Version Bump Rule

Not a flag, but the config obligation most often tripped over. Any content change under a packaged plugin source dir requires a strictly-greater SemVer bump of that tree's `.claude-plugin/plugin.json` (installed caches key off the version; PR #1942 shipped a deleted skill until PR #2114 caught it by hand; incident home: `ai-agents-failure-archaeology`).

| Tree | plugin.json | Version as of 2026-07-03 |
|---|---|---|
| `.claude/` | `.claude/.claude-plugin/plugin.json` | 0.5.254 |
| `src/claude/` | `src/claude/.claude-plugin/plugin.json` | 0.3.29 |
| `src/copilot-cli/` | `src/copilot-cli/.claude-plugin/plugin.json` | 0.5.254 |

Enforced twice: locally by pre-push section 11c calling `build/scripts/validate_plugin_version_bump.py` (`.githooks/pre-push:1037-1050`) and in CI by `.github/workflows/validate-plugin-version-bump.yml`. A `plugin.json`-only edit needs no bump; any other file in the tree does.

## Hook Registration Surfaces

Two registration files, kept in sync BY HAND (a known-weak point, see `ai-agents-architecture-contract`):

| Surface | Consumer | Shape as of 2026-07-03 |
|---|---|---|
| `.claude/settings.json` | Claude Code direct | 23 matcher groups across 8 events (PreToolUse 11, SessionStart 2, UserPromptSubmit 1, PostToolUse 5, Stop 1, SubagentStop 1, PreCompact 1, PermissionRequest 1) |
| `.claude/hooks/hooks.json` | Plugin packaging twin | Hand-ported and ALREADY DIVERGENT as of 2026-07-03: 21 groups across 7 events; PreCompact and one SessionStart group are absent vs settings.json (known-weak point, `ai-agents-architecture-contract` Phase 7) |

If you register a hook in one file only, one harness silently lacks it. Check both in any hook PR.

## How to Add a New Flag

- [ ] Define it in exactly one module (single source of truth). Name it for its scope: `SKIP_ACTIONLINT` not `SKIP_CHECKS`.
- [ ] Document semantics including the failure mode: what happens when unset, when the guarded thing is broken, and whether the consumer fails open or closed. There is no neutral default for a missing signal (FM-10, PR #1965).
- [ ] Make every activation observable: print a WARN/SKIP line or emit `EVENT=` telemetry (`guard-maturity` consumes these). A silent bypass is the session 1187 pattern.
- [ ] Scope it to one check. Global bypasses (`SKIP_PREPUSH`) are banned by precedent.
- [ ] Add tests: positive (flag honored), negative (flag absent = enforced), edge (bad value), per TESTING-RIGOR.
- [ ] If the flag lives under `.claude/` or `src/copilot-cli/`, bump that tree's plugin.json.
- [ ] Add a row to this catalog and a re-verify one-liner to Provenance below.
- [ ] Route the change through `ai-agents-change-control` classification (a new escape hatch is never docs-only).

## Anti-Patterns

| Anti-pattern | Why it fails | Do instead |
|---|---|---|
| `SKIP_LSP_GATE=true` because the language server is down | Kills the whole gate for the session | `LSP_DOWN=true` (graceful degradation, auto-recovers) |
| Reintroducing a global bypass | Session 1187: abused 3x in hours; user verdict "You can't be trusted" | Narrow, announced, per-check escapes |
| `[skip-drift-check]` without the checklist | Marker skips the CI job but the bypass job posts unmet obligations; reviewers will bounce it | Document reason, update `templates/README.md`, get code-owner approval |
| Documenting a flag only in CONTRIBUTING.md | Docs drift; `SKIP_PREPUSH`/`SKIP_TESTS` rows are already stale there | The defining script is the source of truth; docs quote it (FM-9) |
| Editing `.claude/lib/hook_utilities/` to change flag behavior | That tree is a generated mirror; next `sync_plugin_lib.py` run reverts you | Edit `scripts/hook_utilities/`, run the sync |
| Claiming `SKIPPED: investigation-only` with code staged | CI backstop diffs staged files against the allowlist | Split the commit or run QA |

## Verification

- [ ] The flag you plan to use still exists: run its Provenance one-liner and get a non-empty hit in the defining file (not only in docs).
- [ ] You used the narrowest applicable escape (per-check env var, line directive over file directive, `LSP_DOWN` over kill switch).
- [ ] The bypass is visible in output (WARN/SKIP line, bypass job summary, or validator notice), not silent.
- [ ] If you added a flag: tests cover honored/absent/bad-value, this catalog has the new row, and the plugin version is bumped if the flag lives in a packaged tree.

## Provenance and Maintenance

Audited 2026-07-03 against the working tree. Sources: files and line numbers cited per row above. Line numbers drift; the greps below are the durable re-verification. Run from repo root. If a grep returns nothing, the flag moved or died: update this catalog before relying on it.

| Fact | Re-verify one-liner |
|---|---|
| SKIP_LSP_GATE, LSP_GATE_MODE | `grep -n "SKIP_LSP_GATE\|LSP_GATE_MODE" .claude/hooks/PreToolUse/invoke_lsp_read_guard.py` |
| LSP_DOWN semantics | `grep -n "LSP_DOWN_ENV" scripts/hook_utilities/lsp_health.py` |
| merge/rebase auto-bypass | `grep -n "MERGE_HEAD" scripts/hook_utilities/lsp_gate_state.py` |
| pre-commit skips (AUTOFIX/ACTIONLINT/YAMLLINT/MEMORY_SYNC) | `grep -n "SKIP_AUTOFIX\|SKIP_ACTIONLINT\|SKIP_YAMLLINT\|SKIP_MEMORY_SYNC" .githooks/pre-commit` |
| pre-push skips (WORKFLOW_LOCAL_TEST/CLI_E2E) | `grep -n "SKIP_WORKFLOW_LOCAL_TEST\|SKIP_CLI_E2E" .githooks/pre-push` |
| SKIP_PREPUSH still removed | `grep -c "SKIP_PREPUSH" .githooks/pre-push` (expect 0) |
| [skip-drift-check] marker + obligations | `grep -n "skip-drift-check" .github/workflows/agent-drift-detection.yml` |
| size-exception | `grep -n "size-exception" scripts/validation/skill_size.py` |
| orphan-ref directives + 50-line window | `grep -n "IGNORE_DIRECTIVE_RE" .claude/skills/orphan-ref-validator/scripts/patterns.py && grep -n "splitlines()\[:50\]" .claude/skills/orphan-ref-validator/scripts/scan.py` |
| investigation allowlist | `grep -n "agents/" scripts/modules/investigation_allowlist.py` |
| docs-only verdict | `grep -n "SKIPPED: docs-only" .agents/SESSION-PROTOCOL.md` |
| plugin bump gate (local) | `grep -n "validate_plugin_version_bump" .githooks/pre-push` |
| plugin versions | `grep -n "\"version\"" .claude/.claude-plugin/plugin.json src/claude/.claude-plugin/plugin.json src/copilot-cli/.claude-plugin/plugin.json` |
| GIT_CONFIG_COUNT injection | `grep -n "GIT_CONFIG_COUNT" tests/conftest.py` |
| pytest markers | `grep -n -A 5 "^markers" pyproject.toml` |
| .env keys | `grep -n "API_KEY\|COMPRESS_TOKENIZER" .env.example` |
| hook registration surfaces | `python3 -c "import json; s=json.load(open('.claude/settings.json'))['hooks']; print({k: len(v) for k, v in s.items()})"` |
| stale CONTRIBUTING rows | `grep -n "SKIP_PREPUSH\|SKIP_TESTS" CONTRIBUTING.md` (stale: neither exists in .githooks/pre-push) |

Known open item: `CONTRIBUTING.md:555-556` documents two removed flags; fix on contact via `ai-agents-change-control` (docs-only class). `COMPRESS_TOKENIZER` consumer not located; verify before documenting it as live.
