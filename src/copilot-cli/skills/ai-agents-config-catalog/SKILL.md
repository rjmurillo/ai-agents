---
name: ai-agents-config-catalog
description: Catalog of every configuration axis in this repo, env vars, commit markers, frontmatter keys, QA skip verdicts, and escape hatches, each with its enforcement point and abuse story, plus the checklist for adding a new flag safely. Use when you say `what does a skip flag do`, `list escape hatches`, `can I skip this gate`, `add a config flag`. Do NOT use for hook runtime behavior (use `agent-harness-reference`) or change gating policy (use `ai-agents-change-control`).
version: 1.0.0
license: MIT
---

# AI Agents Config Catalog

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->
Every flag, marker, and skip semantic in this repo, verified against code as
of 2026-07-03. Hook registration surfaces were rechecked on 2026-08-18. Each
escape hatch exists because a gate sometimes misfires; each one also has an
abuse story or a guard. Before you set any of these, read its row. The house
rule (learned in session 1187, see the Removed Flags section): escape hatches
get teeth or get abused.

Related skills: `ai-agents-change-control` owns when a bypass is allowed; `agent-harness-reference` and `ai-agents-architecture-contract` own what the hooks themselves do; `ai-agents-debugging-playbook` owns triaging a gate that fired on you.

## Triggers

- `what does the skip-drift-check marker do`
- `list escape hatches`
- `can I skip this gate`
- `add a config flag`
- `is this skip marker allowed`

## Process

1. Identify the axis type: env var, commit marker, text directive, frontmatter key, file, or verdict string.
2. Find its row in the tables below. Read the effect AND the guard/abuse column before using it.
3. If you are about to use an escape hatch, confirm the legitimate trigger condition holds (for example, a workflow actually unrunnable under act). Bypassing because a gate is slow or annoying is the session 1187 failure mode.
4. Re-verify the flag in its defining validator with the one-liner in Provenance. Documentation can drift after validator changes.
5. Adding a new flag? Follow the checklist in "How to Add a New Flag" and add a row plus a re-verify one-liner to this catalog.

## Environment Variables: LSP Gate (retired)

The LSP-first runtime gate and its three environment escapes (`SKIP_LSP_GATE`, `LSP_GATE_MODE`, `LSP_DOWN`) were retired in #3216 when ADR-062 was amended to keep LSP-first navigation as static steering only. No environment variable governs it now; the guidance lives in `.claude/rules/lsp-first.md`. Nothing to set, nothing to escape.

## Git Hook Configuration

Lefthook is the sole Git hook manager. `lefthook.yml` declares the events,
filters, named jobs, and validator commands. Do not infer a bypass from a
deleted custom payload. Inspect the named validator's current interface before
using or documenting an environment variable.

## Removed and Stale Flags (do not use, do not reintroduce)

| Name | Status as of 2026-07-03 | Story |
|---|---|---|
| `SKIP_PREPUSH` | REMOVED | Historical: abused 3x within hours of creation (session 1187, retro `.agents/retrospective/2026-02-08-session-1187-skip-prepush-abuse.md`) |
| `SKIP_TESTS` | REMOVED | Historical: stale contributor guidance was removed during the Lefthook migration |

Lesson encoded: a global bypass with no teeth (no telemetry, no approval step) will be reached for under pressure. New escape hatches must be narrow, announced in output, and observable.

## Environment Variables: Tests and Tooling

| Name | Type | Effect | Status | Guard / abuse story | Where defined |
|---|---|---|---|---|---|
| `GIT_CONFIG_COUNT` + `GIT_CONFIG_KEY_0`/`GIT_CONFIG_VALUE_0` | env vars (set by conftest) | Test session injects `commit.gpgsign=false` with command-line precedence so test repos never invoke the user's signing setup | Production test infra | Only sets index 0 when `GIT_CONFIG_COUNT` is unset, so an outer process's config is not clobbered | `tests/conftest.py:35-38` |
| PEP 668 / uv | environment reality | Bare `pip` fails (externally managed env). Everything goes through `uv sync --frozen --extra dev`; skill scripts need `uv run python`, not `python3` (PyYAML lives in the venv) | Production | `ModuleNotFoundError: No module named 'yaml'` means you used the wrong interpreter | `pyproject.toml`, `.python-version` (3.14.6) |
| pytest markers `unit`, `integration`, `safe_push_transport`, `security`, `smoke`, `windows_path` | pytest -m selectors | Filter test classes; `smoke` = real-CLI tests needing auth/credits, nightly only, and the smoke gate asserts they were NOT skipped (issue #2231 item 4); `safe_push_transport` = touches a non-local transport, excluded from pre-push | Production | Marking a test `smoke` to dodge CI is detected by the not-skipped assertion | `pyproject.toml [tool.pytest.ini_options].markers` |

## .env Keys (from .env.example)

Copy `.env.example` to `.env`. Keys as of 2026-07-03: `ANTHROPIC_API_KEY` (MCP servers, skill-learning hook LLM fallback, exact token counts), `PERPLEXITY_API_KEY`, `TAVILY_API_KEY`, `CONTEXT7_API_KEY`, `YDC_API_KEY`, and optional `COMPRESS_TOKENIZER` (tiktoken/anthropic/heuristic, default tiktoken). Everything degrades gracefully when absent per ADR-007; missing keys disable the corresponding MCP or fallback path, they do not break the repo. Note: `COMPRESS_TOKENIZER` appears only in `.env.example`; a code consumer was not located in this audit, treat as possibly vestigial.

## Commit Markers

| Name | Type | Effect | Status | Guard / abuse story | Where defined |
|---|---|---|---|---|---|
| `[skip-drift-check]` | commit message marker | Skips the agent drift detection CI gate for the whole PR (marker in ANY commit subject/body counts) | Production escape hatch with obligations | The bypass job posts a checklist that a human must satisfy: reason documented in PR description, `templates/README.md` updated with the intentional difference, explicit code-owner approval. Marker alone is NOT approval | `.github/workflows/agent-drift-detection.yml:65-69` (detection), `:297-320` (obligations); `CONTRIBUTING.md:499` |

## Text Directives (orphan-ref-validator)

| Name | Type | Effect | Status | Guard / abuse story | Where defined |
|---|---|---|---|---|---|
| `orphan-ref-ignore` HTML comment | line directive | Mutes orphan-reference findings for that one line | Production | Rare in tree, easy to grep; compensating control is human review of any commit adding one (DESIGN-009) | `.claude/skills/orphan-ref-validator/scripts/patterns.py:63` |
| `orphan-ref-ignore-file` HTML comment | file directive | Mutes the whole file, but ONLY if the directive appears within the first 50 lines | Production | The 50-line rule prevents burying the mute at the bottom of a long doc | `patterns.py:89`; 50-line window at `scan.py:234` |

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
| `SKIPPED: investigation-only` | Every staged file matches the allowlist: `.agents/sessions/`, `.agents/analysis/`, `.agents/retrospective/`, `.serena/memories/`, `.agents/security/`, `.agents/memory/` (incl. `episodes/`), `.agents/architecture/REVIEW-*`, `.agents/critique/` | Single source of truth `scripts/modules/investigation_allowlist.py`; pre-check via the `session` skill (Test-InvestigationEligibility); CI backstop `.github/scripts/validate_investigation_claims.py` (advisory, confirmed: exits 0 unconditionally per its own docstring and `main()`) |
| `SKIPPED: docs-only` | All changes are markdown and strictly editorial: spelling, grammar, formatting; no code, config, tests, workflows, or code-block changes | Re-verified 2026-08-18: `SESSION-PROTOCOL.md:754` no longer exists (PR #5135 cut the file to 324 lines and dropped the exact verdict strings; it now only names the exemption generically at Phase 2.5). The enforcing source is `scripts/validate_session_json.py` (`validate_qa_skip_scope`, dispatch table at lines 166-169) plus `CONTRIBUTING.md:695-699` |

Mixed sessions do not qualify; split the commit. Claiming investigation-only with a code file staged is exactly what the CI backstop exists to catch.

## Plugin Manifest Version Prohibition

Not a flag, but the config obligation most often tripped over. No packaged
plugin manifest may carry a `version` field, and neither may a marketplace
entry. Claude Code resolves freshness from the first version it finds, so a
committed version pins consumers to a hand-bumped string instead of the git
commit SHA (ADR-092, which supersedes ADR-079; issue #4080).

| File | Must not carry |
|---|---|
| `.claude/.claude-plugin/plugin.json` | `version` |
| `src/claude/.claude-plugin/plugin.json` | `version` |
| `src/copilot-cli/.claude-plugin/plugin.json` | `version` |
| `.claude-plugin/marketplace.json` (per entry) | `version` |
| `.github/plugin/marketplace.json` (per entry) | `version` |

Enforced locally by the `pre-pr-validation` job in `lefthook.yml`, which runs
`scripts/validation/pre_pr.py`; that runner invokes
`build/scripts/validate_plugin_version_bump.py`. CI also enforces it through
`.github/workflows/validate-plugin-version-bump.yml`, which fires on a plugin
source dir or a marketplace file. A content change needs no manifest edit at
all.

## Hook Registration Surfaces

Three independent registration sources serve different consumers. Do not force
parity between them:

| Surface | Consumer | Shape re-verified 2026-08-18 |
|---|---|---|
| `.claude/settings.json` | Claude Code direct in this repository | 6 events, 7 groups |
| `.claude/hooks/hooks.json` | Vendored plugin source for both harness packages | 1 events, 1 groups |
| `.github/hooks/require-subagent-model.json` | Copilot CLI in this repository (cloud agent from the default branch) | native `preToolUse`, matcher `task`, direct registration |

The Copilot generator reads `.claude/hooks/hooks.json`, not local settings. A
one-file registration is valid only when its consumer scope is deliberate.
Check both sources in any hook PR and document repository-only versus vendored
intent.
No `PermissionRequest` policy hook is registered. Test runners execute
repository-controlled code, so command-name matching is not a safe approval boundary.

## How to Add a New Flag

- [ ] Define it in exactly one module (single source of truth). Name it for its scope: `SKIP_ACTIONLINT` not `SKIP_CHECKS`.
- [ ] Document semantics including the failure mode: what happens when unset, when the guarded thing is broken, and whether the consumer fails open or closed. There is no neutral default for a missing signal (FM-10, PR #1965).
- [ ] Make every activation observable: print a WARN/SKIP line, or emit `EVENT=` telemetry if you also ship a consumer for it (the previous guard-maturity consumer was retired under ADR-084, issue #5154, and nothing reads that schema today). A silent bypass is the session 1187 pattern.
- [ ] Scope it to one check. Global bypasses (`SKIP_PREPUSH`) are banned by precedent.
- [ ] Add tests: positive (flag honored), negative (flag absent = enforced), edge (bad value), per TESTING-RIGOR.
- [ ] If the flag lives under `.claude/`, regenerate the `src/copilot-cli/` mirror. Do not touch plugin.json; it carries no version.
- [ ] Add a row to this catalog and a re-verify one-liner to Provenance below.
- [ ] Route the change through `ai-agents-change-control` classification (a new escape hatch is never docs-only).

## Anti-Patterns

| Anti-pattern | Why it fails | Do instead |
|---|---|---|
| Reintroducing a global bypass | Session 1187: abused 3x in hours; user verdict "You can't be trusted" | Narrow, announced, per-check escapes |
| `[skip-drift-check]` without the checklist | Marker skips the CI job but the bypass job posts unmet obligations; reviewers will bounce it | Document reason, update `templates/README.md`, get code-owner approval |
| Documenting a flag only in CONTRIBUTING.md | Docs drift previously left removed flags in active guidance | The defining script is the source of truth; docs quote it (FM-9) |
| Editing `.claude/lib/hook_utilities/` to change flag behavior | That tree is a generated mirror; next `sync_plugin_lib.py` run reverts you | Edit `scripts/hook_utilities/`, run the sync |
| Claiming `SKIPPED: investigation-only` with code staged | CI backstop diffs staged files against the allowlist | Split the commit or run QA |

## Verification

- [ ] The flag you plan to use still exists: run its Provenance one-liner and get a non-empty hit in the defining file (not only in docs).
- [ ] You used the narrowest applicable escape (per-check env var, line directive over file directive).
- [ ] The bypass is visible in output (WARN/SKIP line, bypass job summary, or validator notice), not silent.
- [ ] If you added a flag: tests cover honored/absent/bad-value, and this catalog has the new row. No manifest bump even when the flag lives in a packaged tree: the manifests carry no version (ADR-092).

## Provenance and Maintenance

Audited 2026-08-18 against the working tree for hook registration surfaces.
Other rows remain verified as of 2026-07-03. Sources: files and line numbers
cited per row above. Line numbers drift; the commands below are the durable
re-verification. Run from repo root. If a command returns nothing, the flag
moved or died: update this catalog before relying on it.

| Fact | Re-verify one-liner |
|---|---|
| Git hook jobs, filters, and validators | `uv run --frozen lefthook validate` |
| [skip-drift-check] marker + obligations | `grep -n "skip-drift-check" .github/workflows/agent-drift-detection.yml` |
| size-exception | `grep -n "size-exception" scripts/validation/skill_size.py` |
| orphan-ref directives + 50-line window | `grep -n "IGNORE_DIRECTIVE_RE" .claude/skills/orphan-ref-validator/scripts/patterns.py && grep -n "splitlines()\[:50\]" .claude/skills/orphan-ref-validator/scripts/scan.py` |
| investigation allowlist | `grep -n "agents/" scripts/modules/investigation_allowlist.py` |
| docs-only verdict | `grep -n "SKIPPED: docs-only" CONTRIBUTING.md scripts/validate_session_json.py` (SESSION-PROTOCOL.md no longer names the exact verdict string as of PR #5135) |
| plugin version-field validator | `uv run python build/scripts/validate_plugin_version_bump.py --help` |
| no version in any manifest or marketplace entry | `uv run python build/scripts/validate_plugin_version_bump.py` |
| GIT_CONFIG_COUNT injection | `grep -n "GIT_CONFIG_COUNT" tests/conftest.py` |
| pytest markers | `grep -n -A 5 "^markers" pyproject.toml` |
| .env keys | `grep -n -e "API_KEY" -e "COMPRESS_TOKENIZER" .env.example` |
| hook registration surfaces | `uv run --frozen python -c "import json; s=json.load(open('.claude/settings.json'))['hooks']; print({k: len(v) for k, v in s.items()})"` |
| repository-local Copilot sub-agent gate | `uv run --frozen python -c "import json; h=json.load(open('.github/hooks/require-subagent-model.json'))['hooks']['preToolUse']; print([(e['matcher'], e['type']) for e in h])"` |
| removed flags absent from CONTRIBUTING | `grep -n -e "SKIP_PREPUSH" -e "SKIP_TESTS" CONTRIBUTING.md` (expect no matches) |

`COMPRESS_TOKENIZER` consumer not located; verify before documenting it as live.
