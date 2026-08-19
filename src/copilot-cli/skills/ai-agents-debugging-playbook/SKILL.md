---
name: ai-agents-debugging-playbook
version: 1.0.0
license: MIT
description: Symptom-to-triage playbook for this repo's recurring failures. Blocked pushes, drift gate reds, plugin bump reds, coverage pin trips, hook exit 143, session NON_COMPLIANT. Maps each symptom to a first command, discriminating experiment, fix path, and trap. Use when you say `triage this failure`, `why is my push blocked`, `debug this CI red`. Do NOT use for incident history (use `ai-agents-failure-archaeology`) or measurement tools (use `ai-agents-diagnostics-toolkit`).
---

# ai-agents Debugging Playbook

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, .github/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->
Symptom-first triage for this repository's known failure modes. Every row below was earned by a real incident; the retro path is cited so you can read the full story. The playbook answers one question: given this symptom, what is the FIRST command to run, what experiment discriminates between causes, and what trap has already cost someone real time here?

Vocabulary used once: a "guard" is a PreToolUse or pre-push hook that can block an action (exit 2 blocks, exit 0 allows). A "drift gate" is a CI check that fails when a generated tree no longer matches its canonical source. A "discriminating experiment" is one cheap action whose outcome splits the hypothesis space in two.

## Triggers

- `triage this failure`
- `why is my push blocked`
- `debug this CI red`
- `what does this gate failure mean`
- `hook blocked my tool call`

## When NOT To Use This Skill

| You want | Use instead |
|----------|-------------|
| The full history of an incident (root cause, evidence, what changed) | `ai-agents-failure-archaeology` |
| To measure something (budgets, telemetry, drift as a number) | `ai-agents-diagnostics-toolkit` |
| Evidence standards, test layout, how to write the missing test | `ai-agents-validation-and-qa` |
| The catalog of every env var, marker, and escape hatch | `ai-agents-config-catalog` |
| How the harness itself behaves (payload shapes, plugin roots) | `agent-harness-reference` |
| Fix a NON_COMPLIANT session log | `session-log-fixer` |
| Resolve merge conflicts | Agent: merge-resolver |
| Query agent JSONL event logs | `observability` |

## Process

### Phase 1: Match the symptom

Find your symptom in the master table. Run the first command exactly as written (from repo root). Do not guess at fixes before the discriminating experiment tells you which cause you have.

#### Local blocks (a hook stopped you)

| Symptom | First command | Discriminating experiment | Fix path | Trap |
|---------|---------------|---------------------------|----------|------|
| Push rejected by a guard, stderr shows `EVENT={...}` | Read the EVENT JSON on stderr; the `guard` field names which of `.claude/hooks/PreToolUse/invoke_*_guard.py` fired | Is `outcome` a block or `fail_open`? A block means the guard did its job; `fail_open` means guard infra broke | Fix the underlying violation, then re-push. No tier-classifier consumes this telemetry today; the guard-maturity skill that did was retired under ADR-084 (issue #5154) | Bypassing instead of fixing. SKIP_PREPUSH was abused 3x within an hour of creation and removed (retro `2026-02-08-session-1187-skip-prepush-abuse.md`) |
| `ModuleNotFoundError: No module named 'yaml'` running a skill script | Re-run with `uv run python <script>` | Does `uv run python -c "import yaml"` succeed while `python3 -c "import yaml"` fails? Then it is interpreter resolution, not a missing dep | Always use `uv run python` for `.claude/skills/*/scripts/`; they import `github_core` which needs PyYAML from the project venv | Bare `pip install` fails under PEP 668 on this machine. Everything goes through uv |
| `markdown-autofix`/`markdown-check` blocks the commit, or lint "fixed" files you never touched | `git status` to see the blast radius | Did you run `markdownlint --fix '**/*.md'` (unscoped)? | Revert unrelated files; lint ONLY changed files. The Lefthook job itself is scoped to staged .md files (`lefthook.yml` `markdown-autofix`/`markdown-check`, `glob: "**/*.md"` against `{staged_files}`) | PR #908: an unscoped `markdownlint --fix **/*.md` reformatted memory files repo-wide; the PR hit 59 commits / 95 files (retro `2026-01-15-pr-908-comprehensive-retrospective.md`). The PreToolUse markdownlint guard that originally enforced this was removed under ADR-084 (issue #5154); the same scoping now lives in the two Lefthook jobs named above |
| Bot review thread flags an em-dash or en-dash | `grep -rnP '[\x{2013}\x{2014}]' <your changed files>` | Is the hit under `tests/hooks/fixtures/`? That prefix is exempt | Replace with comma, colon, parentheses, or hyphen (`.claude/rules/universal.md` MUST NOT 5; validator `scripts/validation/checks_dash.py`) | Each dash costs one or more bot threads per PR. Fix all occurrences, not just the flagged one |

#### CI reds (a gate failed on the PR)

| Symptom | First command | Discriminating experiment | Fix path | Trap |
|---------|---------------|---------------------------|----------|------|
| Any CI failure you did not expect | Check whether the same job fails on main before touching your branch | Same failure on main = pre-existing, not yours; file or link an issue instead of "fixing" your PR | Memory `.serena/memories/ci-infrastructure-observations.md` (PR #1361) | Hours misattributed to PR code when main was already red |
| Drift gate red (generated tree differs from source) | Identify which of the 4 surfaces failed, then run its local command: `uv run python build/generate_agents.py --validate`, `uv run python build/scripts/build_all.py --check`, `uv run python ./scripts/sync_plugin_lib.py --check`, `uv run python ./scripts/validation/run_install_parity_ci.py` (build_all imports PyYAML; bare `python3` fails in a fresh shell, see `ai-agents-generation-and-release`) | Ask the DIRECTION question before editing anything: which tree is canonical here? Agents: `templates/agents/*.shared.md` is source. Rules/skills/hooks/commands: `.claude/` is source | Edit the canonical tree, regenerate, commit source and generated together (`ai-agents-generation-and-release`) | 2025-12-15 disaster: agent edited the SOURCE to match the GENERATED tree; drift output shows a difference, not a direction (retro `2025-12-15-drift-detection-disaster.md`) |
| Plugin version-field gate red (`VERSION FIELD PRESENT`) | Read the failure list from `python3 scripts/validation/run_plugin_version_bump_ci.py` (workflow `validate-plugin-version-bump.yml`) | Which file carries the field? The gate names it: one of the three `.claude-plugin/plugin.json` manifests, or an entry in `.claude-plugin/marketplace.json` or `.github/plugin/marketplace.json` | DELETE the `version` key from the named file, then re-run `python3 build/scripts/validate_plugin_version_bump.py` until it prints `plugin-version-bump: OK` | The gate inverted in ADR-092 (supersedes ADR-079): it now fails on the field's PRESENCE. Adding a version back to clear a red gate makes it permanently red. Parity no longer covers versions; `check_plugin_manifest_parity.py` checks description component counts only |
| Coverage pin trips at ~63% (or another surprise number) | Re-run the pinned step's EXACT file list locally, e.g. `pytest tests/test_ai_review.py tests/test_verdict.py tests/test_quality_gate.py --cov=scripts.ai_review_common.verdict --cov-branch --cov-fail-under=100` | Does the number change when you add/remove test files? The pin is file-set sensitive (issue #1963): running one file alone reports 63% | Run all files that exercise the module; add tests for genuinely uncovered branches (`.github/workflows/pytest.yml:137-165`) | `--cov` must use module-name form. The file-path form produced "Module never imported" + 0% with pytest-cov 7.x on Python 3.14 (issue #2063, tested in PR #2078). Do not switch forms without re-verifying both locally and in CI |
| Syntax gate fails on code that runs fine locally | `python3 scripts/validation/validate_python_syntax.py` | Does the flagged construct exist only in Python 3.14 (e.g. PEP 758 unparenthesized except clauses)? | Rewrite to parse at the support floor. The gate compiles every tracked file at the 3.10 floor grammar, not the 3.14 dev target (issue #2655, `scripts/validation/validate_python_syntax.py:2-49`) | "It passes on my 3.14" is exactly the failure the gate exists to catch: a 3.13 host would wedge on import |
| Test fails with `#2316: this test mutated the REAL repo HEAD` | Read the failing test for real `git commit`/`checkout`/`reset` calls | Does the test pass when its git ops target a `tmp_path` repo? | Point all git mutation at a temp repo fixture; the root `conftest.py:46` snapshots HEAD and fails any test that moves it | The corruption shows up in whichever test the checker runs after, not necessarily the guilty one |

#### Copilot CLI runtime failures

| Symptom | First command | Discriminating experiment | Fix path | Trap |
|---------|---------------|---------------------------|----------|------|
| Hook "errored" under Copilot CLI, exit code 143 | Get the exit code from the process log; 143 = SIGTERM, Copilot kills hooks at a 2-3s budget | Exit 2 = the hook itself crashed (often payload shape); exit 143 = timeout. Same "hook errored" surface, different root causes (retro `2026-06-02-issue-2290-copilot-hook-payload-format.md:27`) | Reduce per-hook work; ADR-068 consolidates to one dispatcher per event. Contract details: `agent-harness-reference` | Exit 143 was flagged P0 and unresolved in the #2290 retro (as of 2026-07-02); verify current status before assuming it is fixed |
| Hook reads wrong/missing payload fields under Copilot CLI | Check the event key casing in the hook config | camelCase event keys deliver `toolName`/`toolArgs` (args as a JSON string); PascalCase delivers `tool_name`/`tool_input` | Use PascalCase event keys so payloads match what hook scripts expect (memory `.serena/memories/copilot-hooks-observations.md`, session fix/2290) | Vendor docs omit this contract; it was settled by empirical probe, not documentation |

### Phase 2: Run the discriminating experiment

Before writing any fix, answer three questions in order:

1. Does it reproduce on main? If yes, it is not your PR. Stop debugging your branch.
2. Is the gate doing its job, or is the gate broken? A guard block with a clear violation message is the gate working; fix the violation. A `fail_open` EVENT, a timeout, or a gate red that reproduces on main is gate infrastructure; file it, do not route around it.
3. If it is a drift red: which tree is canonical? Never edit until you can answer this from `AGENTS.md` or the generator docstring, not from the diff.

If three read-only commands have not identified the cause, stop and escalate to a real investigation (`analyze` skill) instead of shotgun-fixing. If you are looping on the same failed fix, `stuck-detection` names the pattern.

### Phase 3: Fix, then prove it locally

1. Apply the fix on the canonical surface only.
2. Re-run the exact failing check locally, not a proxy for it:
   - Tests: `uv run pytest tests/ -x` (new skill tests belong in `tests/skills/<name>/`; the default bundle runner reaches legacy colocated suites, while direct legacy-path invocation is only for targeted diagnosis)
   - Full shift-left sweep: `uv run python scripts/validation/pre_pr.py` (exit codes per ADR-035: 0 ok, 1 logic, 2 config)
   - Drift: the specific surface command from the table above
3. Prove the check can still fail. Re-run it with a deliberate defect injected; a gate that prints OK both ways is not covering your change. Three here pass in ways that read as success: `validate_install_parity.py` is a co-change check, not a content comparison, and it skips RULE groups entirely (`:378`) and exempts diffs touching only hand-maintained agent copies (`:389`); that script and `run_plugin_version_bump_ci.py` both diff a base ref, so an uncommitted control is invisible and you must commit the control first; and `detect_agent_drift.py` compares only the 18 headings named in its `SECTIONS_TO_COMPARE` allowlist (`:57-76`), at an 80 percent similarity threshold (`:668`), whose exit code `.github/workflows/drift-detection.yml:35-42` captures and discards. Anything under an unlisted heading is never compared at all: replacing all 22 agent names in the orchestrator's capability matrix in one install copy still reports "OK (100.0% similar)" and exits 0.
4. Commit with the discipline gates expect: 5 files or fewer per commit. Plan for 20 commits per PR; validation may allow 40 after a qualifying base merge (`git rev-list --count HEAD ^origin/main`).
5. Escape hatches (`[skip-drift-check]`, etc.) require documented justification and are cataloged in `ai-agents-config-catalog`. Using one IS the incident report; say so in the PR.

## Traps That Cost Real Time

One line each; read the retro before repeating history. All paths relative to repo root.

| Trap | Story | Retro |
|------|-------|-------|
| Drift direction inversion | Agent "fixed" drift by editing the source-of-truth tree to match the generated tree; wrong direction, reverted | `.agents/retrospective/2025-12-15-drift-detection-disaster.md` |
| Escape-hatch abuse | SKIP_PREPUSH used 3x within an hour of its creation to dodge validation; user verdict was a trust failure, hatch removed | `.agents/retrospective/2026-02-08-session-1187-skip-prepush-abuse.md` |
| Unscoped tooling | Repo-wide `markdownlint --fix` reformatted files far outside the change; PR ballooned to 59 commits / 95 files | `.agents/retrospective/2026-01-15-pr-908-comprehensive-retrospective.md` |
| Fix built on analogy, not probe | First #2205 hook fix assumed an env var by analogy and added 3 new defects; the working fix came from an empirical probe of Copilot CLI 1.0.57 | `.agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md` |
| Two failures, one symptom | "Hook errored" hid both a payload-casing crash (exit 2) and a SIGTERM timeout (exit 143); fixing one masked the other | `.agents/retrospective/2026-06-02-issue-2290-copilot-hook-payload-format.md` |
| Mitigation reproduces the disease | A mitigation PR shipped a threshold that could never fire (set to 6, repo max was 4) and guards never run on their own branch | `.agents/retrospective/2026-05-10-pr-1989-recursive-failure.md` |
| Guards that prevent nothing | 69 commits of guard framework; the Phase-6 audit found the guards would have prevented 0 of its own 35 fix commits | `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md` |

Deeper history and the settled-battles list live in `ai-agents-failure-archaeology`. The 11-pattern failure catalog is `.agents/governance/FAILURE-MODES.md` (numbered sections 1-11, e.g. section 10 silent defaults, section 11 unrun generated artifacts).

## Anti-Patterns

- Editing a generated tree to make a drift gate green. The gate reads difference, not direction; you may be destroying the source of truth.
- Reaching for an escape hatch (`[skip-drift-check]`, etc.) as a first move. Escapes are for infrastructure failure, not friction.
- Debugging your branch before checking main. Reproduce-on-main is the cheapest discriminator in this playbook.
- Treating exit 2 and exit 143 as the same hook failure. They have different root causes and different fixes.
- Switching `--cov` between module-name and file-path forms to "fix" a coverage red. Only the module-name form resolves correctly here.
- Fixing by analogy ("the other CLI sets this env var, so this one probably does"). This repo's rule is empirical probe first; see `ai-agents-empirical-probe-toolkit`.
- Shotgun-fixing after the first hypothesis fails instead of running one discriminating experiment per hypothesis.

## Verification

Before declaring the failure triaged and fixed:

- [ ] The symptom was matched to a table row, and the FIRST command output (not a guess) identified the cause
- [ ] The discriminating experiment was run and its outcome recorded in the session log or PR description
- [ ] The exact failing check passes locally (same command, same file set as CI), not a proxy
- [ ] The check was proven to still fail with a defect injected, so its pass is about your change and not vacuous
- [ ] No escape hatch was used; or if one was, the PR description says which, why, and links the infrastructure issue
- [ ] If the fix touched a canonical surface with mirrors, the drift command for that surface passes and source plus generated are in the same commit

## Provenance and Maintenance

Verified against the working tree on 2026-07-03. Retro-cited short SHAs do not resolve locally even with full history present (~1471 commits as of 2026-07-03); use `.agents/retrospective/` and `.serena/memories/` for archaeology, not `git log`.

| Fact | Source | Re-verify with |
|------|--------|----------------|
| EVENT= stderr telemetry schema | RETIRED: `push_guard_base.py` and every guard built on it were deleted under ADR-084 (issue #5154); no live file defines this schema | N/A. A surviving `EVENT=` emitter with a related but narrower shape (unknown-identity fail-open, not the general guard schema) is `.claude/lib/hook_utilities/guards.py::_emit_skip_event` |
| 4 drift surfaces run in CI | `.github/workflows/validate-generated-agents.yml:165-225` | `grep -n -e "run_install_parity" -e "sync_plugin_lib" -e "build_all" -e "generate_agents" .github/workflows/validate-generated-agents.yml` |
| `[skip-drift-check]` bypass marker | `.github/workflows/agent-drift-detection.yml:17,65-69` | `grep -n "skip-drift-check" .github/workflows/agent-drift-detection.yml` |
| Version-field prohibition | `build/scripts/validate_plugin_version_bump.py` docstring, section RULE | `grep -n "MUST NOT carry" build/scripts/validate_plugin_version_bump.py` |
| No version in any manifest or marketplace entry | three `.claude-plugin/plugin.json` files, both `marketplace.json` files | `python3 build/scripts/validate_plugin_version_bump.py` |
| Coverage pin file-set sensitivity and 63% | `.github/workflows/pytest.yml:137-147` (issue #1963) | `grep -n "63%" .github/workflows/pytest.yml` |
| Module-name --cov form requirement | `.github/workflows/pytest.yml:150-165` (issue #2063, PR #2078) | `grep -n "Module never imported" .github/workflows/pytest.yml` |
| Syntax gate parses at 3.10 floor | `scripts/validation/validate_python_syntax.py:2-49` (issue #2655) | `sed -n '1,50p' scripts/validation/validate_python_syntax.py` |
| Real-HEAD mutation guard | `conftest.py:46-53` (issue #2316) | `grep -n "2316" conftest.py` |
| Exit 143 SIGTERM, P0, unresolved as of retro | `.agents/retrospective/2026-06-02-issue-2290-copilot-hook-payload-format.md:16,27,59` | `grep -n "143" .agents/retrospective/2026-06-02-issue-2290-copilot-hook-payload-format.md` |
| Payload field names depend on event-key casing | `.serena/memories/copilot-hooks-observations.md` | `grep -n "toolName" .serena/memories/copilot-hooks-observations.md` |
| Reproduce-on-main rule (PR #1361) | `.serena/memories/ci-infrastructure-observations.md` | `grep -n "1361" .serena/memories/ci-infrastructure-observations.md` |
| pre_pr.py sequence and exit codes | `scripts/validation/pre_pr.py:1-30` | `sed -n '1,30p' scripts/validation/pre_pr.py` |
| install-parity checks co-change, not content; skips RULE and hand-maintained-only diffs | `build/scripts/validate_install_parity.py:378,389` | `sed -n '376,392p' build/scripts/validate_install_parity.py` |
| Agent drift compares an 18-heading allowlist at 80 percent similarity, reported not enforced | `build/scripts/detect_agent_drift.py:57-76,668`, `.github/workflows/drift-detection.yml:35-42` | `sed -n '57,76p;668p' build/scripts/detect_agent_drift.py; sed -n '35,42p' .github/workflows/drift-detection.yml` |
| testpaths exclude skill tests | `pyproject.toml [tool.pytest.ini_options].testpaths` | `grep -n testpaths pyproject.toml` |
| FAILURE-MODES.md 11 sections | `.agents/governance/FAILURE-MODES.md:32-404` | `grep -n "^## " .agents/governance/FAILURE-MODES.md` |

Maintenance: when a new recurring failure earns a retro, add a table row here with all five columns filled, and update `ai-agents-failure-archaeology` with the history. When any cited line number drifts, fix it on contact using the re-verify command.
