---
name: ai-agents-validation-and-qa
description: What counts as evidence in ai-agents and how to produce it. Covers the TESTING-RIGOR pos+neg+edge bar, test layout and collection reality, coverage proof commands, runtime-contract tests with negative controls, and ADR-034 QA skip semantics at session end. Use when you say `what counts as evidence`, `how do I test this change`, `run skill tests`, `can I skip QA`. Do NOT use for CI failure triage (use `ai-agents-debugging-playbook`) or measurement tooling (use `ai-agents-diagnostics-toolkit`).
version: 1.0.0
license: MIT
---

# ai-agents Validation and QA

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->
This repo runs verification-based governance: a claim is true when a gate, test, or command output says it is, not when an agent asserts it. This skill defines the evidence bar for code changes, where tests live and how they are collected, the anti-pattern canon (each entry paid for by a real incident), and the QA gate semantics at session end.

Audience: a zero-context contributor (human or model) about to write, run, or skip tests in this repository.

## Triggers

- `what counts as evidence`
- `how do I test this change`
- `run skill tests`
- `can I skip QA`

## Scope Boundaries

| You want | Use instead |
|----------|-------------|
| Triage a red CI check or a blocked push | `ai-agents-debugging-playbook` |
| Measure drift, budgets, telemetry, coverage trends | `ai-agents-diagnostics-toolkit` |
| Probe an external tool's runtime behavior empirically | `ai-agents-empirical-probe-toolkit` |
| Understand which gates a change class triggers | `ai-agents-change-control` |
| Session-end mechanics beyond the QA row | `session-end` skill |

## Process

### Phase 1: Internalize the evidence bar

`.agents/governance/TESTING-RIGOR.md` is BLOCKING for code changes (its own Status line, TESTING-RIGOR.md:5). The bar, per function you add or change:

| Requirement | Concretely |
|-------------|-----------|
| Positive test | Valid input produces the expected output |
| Negative test | Invalid input produces the language's idiomatic error, asserted |
| Edge tests | Whitespace, empty, None, wrong type |
| Every error branch | Each `raise` / error-return path exercised |
| Every conditional branch | Including branches that only change user-facing strings |
| Mocked I/O | No live subprocess, API, or file dependencies in unit tests |
| CLI contract | argv-failure exits, exit codes, stdout vs `--output` tested |
| Coverage proof | 100% block coverage on changed files (see Phase 4) |

Origin story: in PR #1756, the original 20 unit tests gave 24% block coverage; adding negative, edge, and branch tests raised it to 100% and caught real defects the happy-path tests missed (whitespace handling on verdict matching, conditional OTHER-hint emission, type validation). That review created TESTING-RIGOR.md (TESTING-RIGOR.md:3-16). The rule exists because bots (Copilot, CodeRabbit, Gemini) reliably catch what happy-path tests skip, at roughly 10x the cost of writing the tests up front (TESTING-RIGOR.md:81).

Coverage targets by risk tier (AGENTS.md Standards; TESTING-ANTI-PATTERNS.md:112-118): 100% security-critical, 80% business logic, 60-70% docs/glue. "Security-critical" includes secret handling, input validation, command execution, path sanitization, auth checks.

Quality trumps quantity: `.agents/governance/TESTING-ANTI-PATTERNS.md` bans coverage theater (assertion-free tests), brittle mocks for impossible scenarios, unit-tests-as-only-testing, quantity over quality, and testing entirely after the fact. A test that never failed during development may not be testing anything (TESTING-ANTI-PATTERNS.md:91).

### Phase 2: Know where tests live and how they are collected

pytest collects only `testpaths = ["tests"]` (pyproject.toml:61). Everything else runs explicitly.

| Location | Collected by default | What lives there | Run it |
|----------|---------------------|------------------|--------|
| `tests/` | Yes | Root suite: scripts, hooks (`tests/hooks/`), build scripts (`tests/build_scripts/`), workflows, harness-specific suites (`tests/claude_mem/`, `tests/forgetful/`, `tests/claude/skills/`) | `uv run pytest tests/ -x` |
| `tests/skills/NAME/` | Yes | Tests for a skill's Python scripts (importable via conftest sys.path) | `uv run pytest tests/skills/github/ -x` |
| `.claude/skills/NAME/tests/` | NO | Per-skill structure tests, colocated with the skill (claude-agents.md MUST 3) | `uv run pytest .claude/skills/NAME/tests/ -q` |

Two skill-test locations is a real fork, not a typo: structure tests colocate under `.claude/skills/NAME/tests/` and are NOT collected by `uv run pytest tests/ -x`; behavior tests for skill scripts land in `tests/skills/NAME/` and are. CI pins only the second location (`.github/workflows/pytest.yml:214-222` runs `tests/skills/github/test_wait_for_unresolved_zero.py`); no workflow collects `.claude/skills/*/tests/` at all, so those files run only when you name them explicitly (issue #3593, `.agents/retrospective/2026-07-28-autopilot-issue-burndown.md:72-74`). When you add a skill, you usually need both (Phase 6).

Useful invocations, all verified (as of 2026-07-03):

```bash
uv run pytest tests/ -x                                    # full default suite, stop on first failure
uv run pytest tests/test_ai_review.py -x                   # one file
uv run pytest tests/ -m unit                               # by marker
uv run pytest .claude/skills/prose-self-check/tests/ -q    # one skill's colocated tests
uv run pytest .claude/skills/NAME/tests/ --collect-only -q # prove tests are discoverable without running
```

Markers (pyproject.toml:66-72): `unit`, `integration`, `safe_push_transport`, `security`, `smoke`. `safe_push_transport` means the test touches a non-local transport and is excluded from pre-push. `smoke` means real-CLI tests needing auth/credits, nightly only; the smoke gate asserts they were not skipped (issue #2231 item 4). Always `uv run pytest`, never bare `pytest` or `python3 -m pytest` outside the venv: PyYAML and friends live in the uv venv (see `ai-agents-build-and-env`).

Stale doc warning: `.agents/governance/test-location-standards.md` still describes a Pester/`*.Tests.ps1` layout. Zero `*.Tests.ps1` files exist (as of 2026-07-03; ADR-042 Python migration). Trust the table above and pyproject.toml, not that file.

### Phase 3: Write tests that count

Beyond pos+neg+edge, this repo demands five specific disciplines:

**1. Isolation from the real repo.** The root `conftest.py` (repo root, lines 315-386) fails any test that moves the REAL repo HEAD (issue #2316): every git mutation must run in a `tmp_path` repo with `cwd=` that repo. Supporting fixtures in `tests/conftest.py`: `GIT_CONFIG_COUNT` injection neutralizes host `commit.gpgsign` so tmp-repo commits work in signing environments (issue #2548, tests/conftest.py:26-61), and `AI_AGENTS_PROJECT_REPO=1` defaults identity for guards that check the origin remote (issue #2610, tests/conftest.py:64-76). Consumer-repo simulation tests override that env var to `"0"`.

**2. Runtime-contract tests for generated artifacts (FM-11).** A generated artifact that has never been executed is not done (FAILURE-MODES.md:28, index row 11; the #2205 incident wedged every plugin customer for 33 days). `.claude/rules/generated-artifacts.md:67-73` requires: execute the shipped artifact under the host's real contract (foreign cwd, host-set env vars), assert the intended effect, and include a negative control proving the test CAN fail (a bare relative path must fail the same harness). The exemplar is `tests/build_scripts/test_generate_hooks_runtime_contract.py`: see `test_negative_control_bare_relative_path_fails` and `test_anchor_is_load_bearing_when_no_plugin_root_var_set`.

**3. Negative controls beat self-reference.** A test that string-matches the generator's own output passes when the generator is consistently wrong. The first #2205 fix shipped exactly this (retro 2026-06-02-pr-2205-customer-wedge-incident.md:49,83) and it hid two more defects. Every contract test needs a case where the wrong artifact fails.

**4. Threshold detectors need calibration.** Any threshold-based signal (rework count, thread count, file count) must be replayed against roughly the last 5 real merged PRs and shown to fire correctly before shipping. PR #1989's M4 warning shipped with threshold 6 in a repo whose PRs maxed at 4 file edits: it could never fire (retro 2026-05-10-pr-1989-recursive-failure.md:151-157). A detector that cannot fire on recent real work is not calibrated.

**5. Guards run on their own branch.** A PR shipping a pre-push or pre-commit guard must show that guard running against its own branch, terminal output in the PR description (retro 2026-05-10-pr-1989-recursive-failure.md:131-137; M5 was never applied to the PR that shipped it).

### Phase 4: Prove coverage

100% block coverage on changed files, with only defensive-unreachable exclusions (`# pragma: no cover`) plus written justification (TESTING-RIGOR.md:53).

```bash
uv run pytest tests/test_ai_review.py tests/test_verdict.py tests/test_quality_gate.py --cov=scripts.ai_review_common.verdict --cov-branch --cov-fail-under=100
```

Two traps, both fossilized in `.github/workflows/pytest.yml` comments:

| Trap | Rule | Evidence |
|------|------|----------|
| File-set sensitivity | A `--cov-fail-under=100` pin must run EVERY test file that exercises the module. After a test-file split, running one file alone reported 63% and tripped the gate | Issue #1963; pytest.yml:196-205 |
| Coverage target form | Use the module-name form (`--cov=wait_for_unresolved_zero`), never the file-path form. File paths produce "Module never imported" + 0% with pytest-cov 7.x on Python 3.14 | Issue #2063, tested in PR #2078; pytest.yml:207-222 |

Related discipline, FM-10: there is no neutral default for a missing signal (FAILURE-MODES.md:387). The neutral default is UNKNOWN, not PASS (`extract_verdict` on no-match, `merge_verdicts` on empty; `get_verdict` fails safe to CRITICAL_FAIL). PR #1965 still took 3 fix rounds to make UNKNOWN blocking everywhere it flowed: the workflow verdict list, the action parser allowlist, and the action exit-code mapping. When testing parsers or gates, always include the missing-signal case and assert it raises or blocks, never that it silently passes.

### Phase 5: QA gate semantics at session end

Session protocol Phase 2.5 makes QA validation BLOCKING before committing feature code (SESSION-PROTOCOL.md:738-756). Skip classes (ADR-034, `.agents/architecture/ADR-034-investigation-session-qa-exemption.md`):

| Evidence string | When valid | Staged files limited to |
|-----------------|-----------|------------------------|
| `SKIPPED: docs-only` | Strictly editorial doc edits: no code, config, tests, workflows, or code blocks changed | Documentation files |
| `SKIPPED: investigation-only` | No code/config changes at all | The 8 patterns in `scripts/modules/investigation_allowlist.py` (single source of truth per its docstring): `.agents/sessions/`, `.agents/analysis/`, `.agents/retrospective/`, `.serena/memories/`, `.agents/security/`, `.agents/memory/` (incl. `episodes/`), `.agents/architecture/REVIEW-*`, `.agents/critique/`. ADR-034:78-87 lists the same 8 after the 2026-07-08 amendments (issues #831 and #732), so the ADR and the code agree. `SESSION-PROTOCOL.md:754` still lists only the first 5, so treat the module and ADR-034 as authoritative |

Explicitly NOT skippable: `.agents/planning/`, `.agents/architecture/ADR-*` (ADRs; `REVIEW-*` files ARE allowlisted by the enforcement module), `.github/`, `.claude/agents/`, `src/`, `scripts/` (ADR-034 "Not Allowed" table, which predates the module's wider allowlist). Session logs, analysis artifacts, and memory updates are audit trail, not implementation: they are filtered out automatically when deciding whether QA is required, so they can ride along with implementation commits (SESSION-PROTOCOL.md:758).

Mixed session (investigation turned into code)? Split it: commit investigation work with the skip evidence, then start a new session for the code change with real QA (SESSION-PROTOCOL.md:798-800). Abusing skip markers is a trust failure with precedent; escape-hatch history lives in `ai-agents-config-catalog` and `ai-agents-failure-archaeology`.

Full evidence line in the session log looks like `"qaValidation": { "level": "MUST", "Complete": true, "Evidence": "SKIPPED: investigation-only" }` or a QA report path under `.agents/qa/` (SESSION-PROTOCOL.md:996).

### Phase 6: Add tests for a new skill, hook, or script

- [ ] Skill: create `.claude/skills/NAME/tests/test_skill_structure.py` (frontmatter, sections, size, dash checks; copy the shape from `.claude/skills/prose-self-check/tests/`). Required by `.claude/rules/claude-agents.md:18` (MUST 3).
- [ ] Skill scripts with behavior: add `tests/skills/NAME/test_SCRIPT.py` so the default suite collects them; add `__init__.py` and a `conftest.py` for sys.path if importing the script by module name.
- [ ] Hook: add `tests/hooks/test_NAME.py`; use `tests/hook_test_helpers.py`; cover exit 0 (allow, stdout context), exit 2 (block, stdout message), and malformed-stdin input.
- [ ] Validation/build script: add `tests/test_NAME.py` or `tests/build_scripts/test_NAME.py`; test exit codes per ADR-035 (0 ok, 1 logic, 2 config, 3 external, 4 auth).
- [ ] Generated artifact: add a runtime-contract test with a negative control (Phase 3, item 2).
- [ ] All git-mutating tests isolated in `tmp_path` repos (the #2316 guard will fail you otherwise).
- [ ] Prove collection: `uv run pytest PATH --collect-only -q` shows your tests; then run them; then run the coverage pin form from Phase 4 on changed files.
- [ ] Run `python3 scripts/validation/pre_pr.py` before the PR (the local shift-left aggregate; see `ai-agents-change-control` for the full gate ladder).

## Anti-Patterns

Each row cost real time. Do not re-earn these lessons.

| Anti-pattern | Incident | Binding rule |
|--------------|----------|--------------|
| Self-referential test (asserts generator output against itself) | First #2205 fix shipped one; it passed while the artifact was broken (retro :49, :83) | Runtime-contract test + negative control (generated-artifacts.md:67-73) |
| Happy-path-only test suite | PR #1756: 20 tests, 24% coverage, bots caught the rest | TESTING-RIGOR.md pos+neg+edge, BLOCKING |
| Threshold detector never calibrated | #1989 M4: threshold 6, repo max 4, could never fire | Calibration table against last ~5 real PRs before commit |
| Guard not run on its own branch | #1989 M5: bot-cascade hook shipped but never applied to its own PR | Guard output on the shipping branch in the PR description |
| Test mutates the real repo | Repo-root conftest.py:315-386 (#2316) | Isolate in `tmp_path`, run git with `cwd=` the tmp repo |
| Silent default for missing signal | PR #1965 verdict parser defaulted missing to PASS, 3 fix rounds (FM-10) | Test the missing-signal case; assert raise/block |
| Coverage theater (assertion-free tests, tautologies) | Issue #749 philosophy work | TESTING-ANTI-PATTERNS.md 1: each test answers a stakeholder concern |
| Trusting the Pester test-location doc | `test-location-standards.md` predates ADR-042; zero `.Tests.ps1` files remain | Use Phase 2 table + pyproject.toml:61 |
| Skipping QA on a mixed session | ADR-034 allowlist exists precisely to fence this | Split the session; skip evidence only with allowlisted paths staged |

## Verification

Before claiming a change meets the evidence bar:

- [ ] Every new/changed function has pos, neg, and edge tests; every error and conditional branch exercised
- [ ] External I/O mocked in unit tests; CLI exit codes tested where a CLI changed
- [ ] `uv run pytest tests/ -x` green locally, plus explicit runs for any `.claude/skills/NAME/tests/` you touched
- [ ] Coverage proven at 100% on changed files using the module-name `--cov` form
- [ ] Generated artifacts have a runtime-contract test with a negative control
- [ ] Any new threshold or guard shows calibration/self-application evidence in the PR description
- [ ] QA row in the session log carries a report path or a legal `SKIPPED:` evidence string with allowlisted staged files

## Provenance and Maintenance

Verified 2026-07-29 against the working tree (issue #3828 re-verification pass; the earlier 2026-07-03 pass had rotted for `pyproject.toml`, both `conftest.py` files, `.github/workflows/pytest.yml`, and `.claude/rules/generated-artifacts.md`). Sources: `.agents/governance/TESTING-RIGOR.md:3-55,77-81`, `.agents/governance/TESTING-ANTI-PATTERNS.md:9-118`, `pyproject.toml:60-72`, repo-root `conftest.py:315-386`, `tests/conftest.py:19-76`, `.github/workflows/pytest.yml:196-222`, `.claude/rules/generated-artifacts.md:67-73`, `.claude/rules/claude-agents.md:18`, `.agents/architecture/ADR-034-investigation-session-qa-exemption.md:62-110`, `.agents/SESSION-PROTOCOL.md:738-800,996`, `.agents/governance/FAILURE-MODES.md:14-30,387`, `.agents/retrospective/2026-05-10-pr-1989-recursive-failure.md:110-157`, `.agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md:23-83`.

Re-verify volatile facts:

```bash
grep -n testpaths pyproject.toml                                  # collection roots
sed -n '315,386p' conftest.py                                     # #2316 HEAD guard still present
grep -n "cov-fail-under" .github/workflows/pytest.yml             # coverage pins and forms
grep -n "SKIPPED" .agents/SESSION-PROTOCOL.md | head -5           # QA skip evidence strings
ls tests/skills/ .claude/skills/prose-self-check/tests/           # both skill-test locations alive
git ls-files '*.Tests.ps1' | wc -l                                # Pester doc still stale if 0
```

If TESTING-RIGOR.md, ADR-034, or the pytest.yml pins change, update the matching phase here in the same PR.
