---
name: ai-agents-config-catalog
description: Catalog of every configuration axis in this repo, env vars, commit markers, frontmatter keys, QA skip verdicts, and escape hatches, each with its enforcement point and abuse story, plus the checklist for adding a new flag safely. Use when you say `what does a skip flag do`, `list escape hatches`, `can I skip this gate`, `add a config flag`. Do NOT use for hook runtime behavior (use `agent-harness-reference`) or change gating policy (use `ai-agents-change-control`).
version: 1.0.0
license: MIT
metadata:
  distribution: repo-local
  routing:
    role: conditional-adjunct
    invoker: ai-agents-debugging-playbook
    trigger: ai-agents-debugging-playbook points here for the full catalog of env vars, markers, and escape hatches
    user-facing: false
---

# AI Agents Config Catalog

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths because its audience is repo contributors, not plugin consumers. Declared paths: .claude/lib/hook_utilities, .claude/skills/orphan-ref-validator/scripts/filters.py, .claude/skills/taste-lints/scripts/taste_lints.py, .github/scripts/validate_investigation_claims.py, .project-toolkit/analysis, .project-toolkit/architecture/REVIEW-, .project-toolkit/critique, .project-toolkit/memory, .project-toolkit/retrospective, .project-toolkit/retrospective/2026-02-08-session-1187-skip-prepush-abuse.md, .project-toolkit/security, .project-toolkit/sessions, build/scripts/build_all.py, build/scripts/validate_plugin_version_bump.py, orphan-ref-validator/scripts/patterns.py, scripts/flag_locator.py, scripts/hook_utilities, scripts/modules/investigation_allowlist.py, scripts/validate_session_json.py, scripts/validation/check_push_lock_before_commit.py, scripts/validation/git_hook_policy.py, scripts/validation/pre_pr.py, scripts/validation/skill_size.py, scripts/validation/test_docs_only_eligibility.py, scripts/validation/test_investigation_eligibility.py -->
Every flag, marker, and skip semantic in this repo, verified against code as
of 2026-10-31 (commit 42e409325). Each
escape hatch exists because a gate sometimes misfires; each one also has an
abuse story or a guard. Before you set any of these, read its row. The house
rule (learned in session 1187, see the Removed Flags section): escape hatches
get teeth or get abused.

Related skills: `ai-agents-change-control` owns when a bypass is allowed; `agent-harness-reference` and `ai-agents-architecture-contract` own what the hooks themselves do; `ai-agents-debugging-playbook` owns triaging a gate that fired on you.

## Triggers

- `what does the drift allowlist do`
- `list escape hatches`
- `can I skip this gate`
- `add a config flag`
- `is this skip marker allowed`

## Process

1. Identify the axis type: env var, commit marker, text directive, frontmatter key, file, or verdict string.
2. Find its row in the tables below. Read the effect AND the guard/abuse column before using it.
3. If you are about to use an escape hatch, confirm the legitimate trigger condition holds (for example, a workflow actually unrunnable under act). Bypassing because a gate is slow or annoying is the session 1187 failure mode.
4. Re-verify the flag in its defining validator with `flag_locator.py locate <id>` (see Scripts). Documentation can drift after validator changes.
5. Adding a new flag? Follow the checklist in "How to Add a New Flag" and add a row to this catalog and a `FLAGS` entry to `flag_locator.py` (path in Scripts).

## Git Hook Configuration

Lefthook is the sole Git hook manager. `lefthook.yml` declares the events,
filters, named jobs, and validator commands. Do not infer a bypass from a
deleted custom payload. Inspect the named validator's current interface before
using or documenting an environment variable.

## Removed and Stale Flags (do not use, do not reintroduce)

| Name | Status as of 2026-10-31 | Story |
|---|---|---|
| `SKIP_PREPUSH` | REMOVED | Historical: abused 3x within hours of creation (session 1187, retro `.project-toolkit/retrospective/2026-02-08-session-1187-skip-prepush-abuse.md`) |
| `SKIP_TESTS` | REMOVED | Removed from the pre-push hook during the Lefthook migration, but it outlived that as the env default for `pre_pr.py --skip-tests`, which was parsed and never read; flag, env default, and the `--verbose` beside it were deleted once no gate set `skip_flag` |
| `SKIP_LSP_GATE`, `LSP_GATE_MODE`, `LSP_DOWN` | REMOVED | LSP-first runtime gate retired (ADR-062 amended); guidance is static steering in `.claude/rules/lsp-first.md` |

Lesson encoded: a global bypass with no teeth (no telemetry, no approval step) will be reached for under pressure. New escape hatches must be narrow, announced in output, and observable.

## Environment Variables: Tests and Tooling

| Name | Type | Effect | Status | Guard / abuse story | Where defined |
|---|---|---|---|---|---|
| `GIT_CONFIG_COUNT` + `GIT_CONFIG_KEY_0`/`GIT_CONFIG_VALUE_0` | env vars (set by conftest) | Test session sets `commit.gpgsign=false` with command-line precedence so test repos never invoke the user's signing setup | Production test infra | Clears every inherited `GIT_CONFIG_COUNT` and numbered key first, then sets count 1 and index 0, so the harness's own count (Copilot CLI sets 3) cannot disarm it; the snapshot is restored on teardown. An outer process's git config does not reach test repos | `tests/conftest.py` (locate with `flag_locator.py locate git-config-count`) |
| PEP 668 / uv | environment reality | Bare `pip` fails (externally managed env). Everything goes through `uv sync --frozen --extra dev`; skill scripts need `uv run python`, not `python3` (PyYAML lives in the venv) | Production | `ModuleNotFoundError: No module named 'yaml'` means you used the wrong interpreter | `pyproject.toml`, `.python-version` (3.14.8 on 2026-10-31) |
| pytest markers (list them with `flag_locator.py markers`) | pytest -m selectors | Filter test classes; `smoke` = real-CLI tests needing auth/credits or an installed CLI, run on pull requests by `plugin-cli-smoke.yml` (except `grok` and `hermes`, which no CI leg selects: run them locally with `RUN_CLI_E2E=1`), and the smoke gate asserts they were NOT skipped (the smoke gate's skip assertion); `safe_push_transport` = touches a non-local transport, excluded from pre-push; `claude` / `copilot` / `codex` = the CLI a real-CLI test needs, so each CLI smoke leg selects `smoke and <cli>` | Production | Marking a test `smoke` to dodge CI is detected by the not-skipped assertion | `pyproject.toml [tool.pytest.ini_options].markers` |
| `SKIP_PUSH_LOCK_COMMIT_GUARD` | env var (`=1` exact match) | Bypasses the `push-lock-commit-guard` pre-commit job, which otherwise refuses a commit while a push for the current branch name holds the canonical push-lock file | Production escape hatch | Scoped to one check, not global. Prints `push-lock: commit guard bypassed via SKIP_PUSH_LOCK_COMMIT_GUARD=1` so the bypass is visible in commit output; any other value (`0`, `true`, unset) leaves the guard enforced | `scripts/validation/check_push_lock_before_commit.py` (`SKIP_ENV`); wired as `push-lock-commit-guard` in `lefthook.yml` |
| `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY` | env var (`1` or unset; blank counts as unset) | Controls what `python-tests` runs pre-push. Unset: `pytest --testmon` runs only the tests pytest-testmon selects (best effort, and it misses code a test reaches only through a subprocess), seeding `.testmondata` from main's CI artifact when none exists, so a broken import, a syntax error and any selected failing test block the push and the rest is CI's. `1`: testmon is skipped entirely and every partition executes locally, announced on stderr. Any other value raises rather than quietly doing less | Production opt-in | Scoped to one job, not a bypass: it makes the gate stricter, never weaker, so there is no abuse direction. Validated before a path is chosen, so `true` is reported whichever way selection would have gone | `scripts/validation/git_hook_policy.py`, constant `PYTEST_FULL_SUITE_LOCALLY_ENV` (name), `_validated_full_suite_opt_in` and the short-circuit in `_resolve_pytest_commands` (semantics). Cited by symbol: two earlier line numbers here went stale within a day |
| `AI_AGENTS_PYTEST_WORKERS` | env var (positive integer or `auto`; blank counts as unset) | Overrides the xdist worker count pre-push pytest runs with. Unset or blank: the policy picks the count. Any other value it cannot parse raises rather than falling back to a default the caller did not ask for | Production | Same fail-loud contract as the flag above and validated at the same point, after a version that checked it only inside the executing partitions let an invalid value pass unreported on the collection path | `scripts/validation/git_hook_policy.py`, constant `PYTEST_WORKERS_ENV` (name), `_pytest_parallel_flags` (semantics) |

## .env Keys (from .env.example)

Copy `.env.example` to `.env`. Keys as of 2026-10-31: `ANTHROPIC_API_KEY` (MCP servers, skill-learning hook LLM fallback, exact token counts), `PERPLEXITY_API_KEY`, `TAVILY_API_KEY`, `CONTEXT7_API_KEY`, `YDC_API_KEY` (five active keys), plus one commented optional key, `# COMPRESS_TOKENIZER=tiktoken` (no code consumer found 2026-10-31). Everything degrades gracefully when absent per ADR-007; missing keys disable the corresponding MCP or fallback path, they do not break the repo.

## Commit Markers

| Name | Type | Effect | Status | Guard / abuse story | Where defined |
|---|---|---|---|---|---|
| `drift-allowlist.json` (governance directory) | committed allowlist file (replaces the retired commit-message marker) | Excuses named files from the agent drift gate. Each entry needs an exact repo-relative `path` and a non-empty `reason`; globs, absolute paths, dot-dot segments, duplicates, and unknown keys are rejected (exit 2). Every other drift still fails | Reviewed exception, visible in the PR diff | `generate_agents.py --validate` prints each allowed divergence with its reason and warns on an entry that matched no drift. CODEOWNERS requires the owner on the allowlist file, its loader, and the generator. No commit message skips the drift job | `drift_allowlist.py`; the Intentional divergence section of CONTRIBUTING |

## Text Directives (orphan-ref-validator)

| Name | Type | Effect | Status | Guard / abuse story | Where defined |
|---|---|---|---|---|---|
| `orphan-ref-ignore` HTML comment | line directive | Mutes orphan-reference findings for that one line | Production | Rare in tree, easy to grep; compensating control is human review of any commit adding one (DESIGN-009) | `orphan-ref-validator/scripts/patterns.py` (`IGNORE_DIRECTIVE_RE`) |
| `orphan-ref-ignore-file` HTML comment | file directive | Mutes the whole file, but ONLY if the directive appears within the first 50 lines | Production | The 50-line rule prevents burying the mute at the bottom of a long doc | `patterns.py` (`FILE_IGNORE_DIRECTIVE_RE`); 50-line window in `scan.py` (`text.splitlines()[:50]`) |

Write the directives as HTML comments (`<!-- ... -->`); shown bare here so this catalog does not mute itself.

## Frontmatter Keys (skills)

| Name | Type | Effect | Status | Guard / abuse story | Where defined |
|---|---|---|---|---|---|
| `size-exception: true` | SKILL.md frontmatter | Exempts the file from the 500-line block in the size validator | Escape hatch, must be justified | `taste-lints` only honors it in the first 20 lines of the file; validator prints "size-exception declared" so reviewers see it, and the gate also needs a rationale comment (`RATIONALE_MIN_CHARS`) and a byte limit | `scripts/validation/skill_size.py` (grep `size-exception`); `.claude/skills/taste-lints/scripts/taste_lints.py` (the `lines[:20]` check) |
| `allowed-tools`, `argument-hint` | frontmatter keys | Harness metadata; not flagged as prose refs, since neither key name matches a candidate pattern the orphan-ref scanner tracks | Production | Candidate patterns live in one place | `.claude/skills/orphan-ref-validator/scripts/filters.py` |

## QA Skip Verdicts (ADR-034)

Session-end QA can be skipped only with one of these exact verdict strings in the session log, and only when the staged files qualify.

| Verdict | When legitimate | Enforcement |
|---|---|---|
| `SKIPPED: investigation-only` | Every staged file matches the allowlist: `.project-toolkit/sessions/`, `.project-toolkit/analysis/`, `.project-toolkit/retrospective/`, `.serena/memories/`, `.project-toolkit/security/`, `.project-toolkit/memory/` (incl. `episodes/`), `.project-toolkit/architecture/REVIEW-*`, `.project-toolkit/critique/` | Single source of truth `scripts/modules/investigation_allowlist.py`; pre-check via `scripts/validation/test_investigation_eligibility.py`; CI backstop `.github/scripts/validate_investigation_claims.py` (advisory, confirmed: exits 0 unconditionally per its own docstring and `main()`) |
| `SKIPPED: docs-only` | All changes are markdown and strictly editorial: spelling, grammar, formatting; no code, config, tests, workflows, or code-block changes | The enforcing source is `scripts/validate_session_json.py` (`validate_qa_skip_scope`, plus its dispatch table naming both verdict strings) and the Docs-only row of the `CONTRIBUTING.md` QA table. Pre-check via `scripts/validation/test_docs_only_eligibility.py` |

Mixed sessions do not qualify; split the commit. Claiming investigation-only with a code file staged is exactly what the CI backstop exists to catch.

## Plugin Manifest Version Prohibition

Not a flag, but the config obligation most often tripped over. No packaged
plugin manifest may carry a `version` field, and neither may a marketplace
entry. Claude Code resolves freshness from the first version it finds, so a
committed version pins consumers to a hand-bumped string instead of the git
commit SHA (ADR-092, which supersedes ADR-079).

| File | Must not carry |
|---|---|
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

Two independent registration sources serve different consumers. Do not force
parity between them. The Copilot sub-agent gate
`.github/hooks/require-subagent-model.json` was retired by ADR-097 along with
every tool-call hook.

| Surface | Consumer | Shape on 2026-10-31 (`hook-counts`) |
|---|---|---|
| `.claude/settings.json` | Claude Code direct in this repository | run `hook-counts` (5 events, 8 registrations on 2026-10-31) |
| `.claude/hooks/hooks.json` | Binplaced copy of `src/claude/hooks.json` | run `hook-counts` |

Chain: `templates/hooks/hooks.json` (source) renders to `src/claude/hooks.json` (plugin tree, the Copilot generator input, `settingsSource` in `templates/platforms/copilot-cli.yaml`), then binplaces to `.claude/hooks/hooks.json` (copy). The generator reads the plugin tree, not local settings. A
one-file registration is valid only when its consumer scope is deliberate.
Check both sources in any hook PR and document repository-only versus vendored
intent.
No `PermissionRequest` policy hook is registered. Test runners execute
repository-controlled code, so command-name matching is not a safe approval boundary.

## How to Add a New Flag

- [ ] Define it in exactly one module (single source of truth). Name it for its scope: `SKIP_ACTIONLINT` not `SKIP_CHECKS`.
- [ ] Document semantics including the failure mode: what happens when unset, when the guarded thing is broken, and whether the consumer fails open or closed. There is no neutral default for a missing signal (FM-10).
- [ ] Make every activation observable: print a WARN/SKIP line, or emit `EVENT=` telemetry if you also ship a consumer for it (the previous guard-maturity consumer was retired under ADR-084, and nothing reads that schema today). A silent bypass is the session 1187 pattern.
- [ ] Scope it to one check. Global bypasses (`SKIP_PREPUSH`) are banned by precedent.
- [ ] Add tests: positive (flag honored), negative (flag absent = enforced), edge (bad value), per TESTING-RIGOR.
- [ ] If the flag lives under `.claude/`, regenerate the `src/copilot-cli/` mirror. Do not touch plugin.json; it carries no version.
- [ ] Add a row to this catalog and a `FLAGS` entry in `.claude/skills/ai-agents-config-catalog/scripts/flag_locator.py` (run it as shown in Scripts, via the plugin-root variable).
- [ ] Route the change through `ai-agents-change-control` classification (a new escape hatch is never docs-only).

## Anti-Patterns

| Anti-pattern | Why it fails | Do instead |
|---|---|---|
| Reintroducing a global bypass | Session 1187: abused 3x in hours; user verdict "You can't be trusted" | Narrow, announced, per-check escapes |
| A drift allowlist entry with no real reason | The validator rejects an empty reason; a vague one gets bounced in review | State why the file differs, update `templates/README.md`, get code-owner approval |
| Documenting a flag only in CONTRIBUTING.md | Docs drift previously left removed flags in active guidance | The defining script is the source of truth; docs quote it (FM-9) |
| Editing `.claude/lib/hook_utilities/` to change flag behavior | That tree is a generated mirror; next `build_all.py` run reverts you | Edit `scripts/hook_utilities/`, run `uv run python build/scripts/build_all.py` |
| Claiming `SKIPPED: investigation-only` with code staged | CI backstop diffs staged files against the allowlist | Split the commit or run QA |

## Verification

- [ ] The flag you plan to use still exists: run `flag_locator.py locate <id>` and get a hit in the defining file (not only in docs).
- [ ] You used the narrowest applicable escape (per-check env var, line directive over file directive).
- [ ] The bypass is visible in output (WARN/SKIP line, bypass job summary, or validator notice), not silent.
- [ ] If you added a flag: tests cover honored/absent/bad-value, and this catalog has the new row. No manifest bump even when the flag lives in a packaged tree: the manifests carry no version (ADR-092).

## Scripts

Run the dispatcher from the repo root. `list` shows each row and whether its file exists; `run <id>` execs it.

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/ai-agents-config-catalog/scripts/instruments.py" --repo . list
```

`flag_locator.py` is the dedicated script. Its answers cover only files the catalog attributes to a flag:

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/ai-agents-config-catalog/scripts/flag_locator.py" --repo . locate --list
```

- `locate <id|name>` takes a kebab id or the exact flag name (`AI_AGENTS_PYTEST_WORKERS`) and prints `file:line` for each attributed file. Exit 1 means a file is missing or lost the needle: the flag moved or died, so fix this catalog first.
- `markers` lists pytest markers from `pyproject.toml`. It does not say which CI leg selects them.
- `retired` confirms `SKIP_PREPUSH` and `SKIP_TESTS` are absent from `CONTRIBUTING.md` and `scripts/validation/pre_pr.py`. A name left in another file is out of scope.

Exit codes for both scripts: 0 ok, 1 findings or a missing file, 2 bad arguments or unreadable config, 3 external failure.

Rows that link existing tools: `hook-counts` (owner script in `ai-agents-portability-campaign`), `manifest-version` (`validate_plugin_version_bump.py`), `lefthook-validate`, `qa-investigation-eligible`, `qa-docs-only-eligible`, `drift-allowlist` (`generate_agents.py --validate` prints each allowed divergence and warns on an entry that matched no drift).

## Provenance and Maintenance

Audited against commit 42e409325 on 2026-10-31. Cites name a symbol or a script id, not a line number, because line numbers drift. `reverify.json` holds the machine checks. Run the drift command from the repo root:

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/skill-bootstrap/scripts/bootstrap_drift.py" check --repo . --skills-root .claude/skills --name ai-agents-config-catalog --require
```

`SKIP_TESTS` is also absent from `pre_pr.py`. `pre_pr_sequence.py` still names `--skip-tests` in its `_Gate` docstring, on purpose, to say why `skip_flag` is gone.
