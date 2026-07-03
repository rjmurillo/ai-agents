---
name: ai-agents-diagnostics-toolkit
version: 1.0.0
license: MIT
description: Catalog of this repo's measurement instruments, each with command, current baseline, and interpretation guide. Covers skill size and description budgets, orphan-ref and golden-principles scans, drift gates as signals, guard telemetry and maturity tiers, coverage pins, and the eval harness. Use when you say `measure this`, `read the drift signal`, `check skill budgets`, `guard maturity report`. Do NOT use to fix what you measure (use `ai-agents-debugging-playbook`) or for evidence standards (use `ai-agents-validation-and-qa`).
---

# ai-agents Diagnostics Toolkit

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->
Measure instead of eyeball. Every instrument below is a read-only command that turns a vague worry ("are skills getting bloated?", "did generation drift?") into a number you can compare against a baseline. This file gives you, per instrument: the question it answers, the exact command, the healthy and unhealthy reading, the current repo baseline (as of 2026-07-02), and the trap that has already cost someone time.

Vocabulary, defined once: an "instrument" is a script whose output you read, not a gate you must pass. A "drift gate" is a CI check that fails when a generated tree stops matching its canonical source. "EVENT telemetry" is the one-line JSON a push guard prints to stderr when it runs. A "baseline" is the number the instrument reports on a clean checkout of main; you measure your delta against it.

## Triggers

- `measure this`
- `read the drift signal`
- `check skill budgets`
- `guard maturity report`
- `interpret this scan output`

## Instrument Index

| Instrument | Question it answers | Command (from repo root) |
|---|---|---|
| Description budget | How much standing context do skill descriptions cost? | `uv run python ./scripts/skill_description_budget.py` |
| Skill size | Which SKILL.md files exceed the 300-warn / 500-block line limits? | `uv run python ./scripts/validation/skill_size.py` |
| Orphan refs | Do specs, evals, and manifests reference entities that no longer exist? | `uv run python .claude/skills/orphan-ref-validator/scripts/scan.py` |
| Golden principles | Where does the repo violate GP-001..GP-005 mechanical rules? | `uv run python .claude/skills/golden-principles/scripts/scan_principles.py` |
| Agent drift | Do generated agent files match their templates? | `uv run python build/generate_agents.py --validate` |
| Mirror drift | Do the 7 generated mirror trees match `.claude/` canonical sources? | `uv run python build/scripts/build_all.py --check` |
| Lib drift | Do `.claude/lib/` copies match `scripts/` canonical modules? | `uv run python ./scripts/sync_plugin_lib.py --check` |
| Guard maturity | Which push guards earn their keep? | `uv run python .claude/skills/guard-maturity/scripts/run_report.py` |
| Coverage | Is changed code actually exercised by tests? | `uv run pytest <tests> --cov=<module> --cov-branch` |
| Eval A/B | Did a prompt or agent change alter behavior, measurably? | `uv run python ./scripts/eval/eval-prompt-change.py --scenarios <file> --dry-run` |
| Commit count | Am I approaching the 20-commit PR cap? | `git rev-list --count HEAD ^origin/main` |

## Process

### Phase 1: Pick the instrument

Match the worry to the row in the Instrument Index. Two routing rules:

| If you want to... | Go to |
|---|---|
| Fix the failure an instrument surfaced | `ai-agents-debugging-playbook` |
| Know what counts as test evidence | `ai-agents-validation-and-qa` |
| Prove a runtime hypothesis with a probe | `ai-agents-empirical-probe-toolkit` |
| Regenerate after a drift red | `ai-agents-generation-and-release` |
| Query agent JSONL event logs | `observability` skill (do not duplicate it) |
| Get adoption metrics from git history | `metrics` skill (`collect_metrics.py`) |

### Phase 2: Run it correctly

- Run from the repo root. All commands above assume it.
- Use `uv run python`, not bare `python3`, for anything that imports repo modules (PyYAML lives in the venv; bare `python3` gives `ModuleNotFoundError: No module named 'yaml'`).
- All instruments here are read-only in the modes shown. `build_all.py --check` runs its generators and then restores the owned trees from a snapshot (issue #2440, `build/scripts/build_all.py:893`), so its log prints `Mode: Generate` and `Written: 49` even though nothing changes on disk. Confirm with `git status --porcelain` if suspicious, and see the trap in the drift section below.
- Read the exit code, not just the prose. It is the machine signal:

| Exit code | Convention (ADR-035 / AGENTS.md) | Exceptions |
|---|---|---|
| 0 | Healthy or within limits | `skill_size.py` prints FAIL lines but exits 0 unless `--ci` |
| 1 | Logic finding (budget exceeded, CRITICAL_FAIL, over limit in `--ci`) | |
| 2 | Config error (bad path, bad args) or staleness for `build_all.py --check` | |
| 10 | Violations found | `scan_principles.py` only |

### Phase 3: Read the number against the baseline

Compare against the "Current baseline" column in each guide below. The repo baseline is NOT all green: two instruments are red on main today. What matters for your change is the delta: your PR should add zero new findings, and should not grow a budget without saying so.

### Phase 4: Act on the reading

Green and unchanged: move on. Red where the baseline was green: your change caused it; triage via `ai-agents-debugging-playbook`. Red where the baseline was already red: not yours to fix silently, but flag it (see-something-say-something) and keep your delta clean.

## Instrument Guides

### Description budget

Every skill description is resident in context on every turn, before any work begins. This instrument sums them (issue #2794).

```bash
uv run python ./scripts/skill_description_budget.py --top 10
uv run python ./scripts/skill_description_budget.py --output-format json
uv run python ./scripts/skill_description_budget.py --max-total-tokens 8000   # gate mode, exit 1 over budget
```

- Current baseline (as of 2026-07-03): 92 skills, 35892 chars, ~8973 estimated tokens; top offenders `analyze` and `pr-comment-responder` at 558 chars each.
- Healthy: total flat or falling; a new skill adds roughly 350-500 chars (house style), hard cap 1024 (`DESCRIPTION_MAX_LENGTH = 1024`, `.claude/skills/SkillForge/scripts/validate-skill.py:171`).
- Unhealthy: total climbing PR over PR with no budget flag set; any single description near 1024.
- Trap: the token figure is a chars/4 heuristic, deliberately not tiktoken. Trend it; never quote it as an exact cost.

### Skill size

```bash
uv run python ./scripts/validation/skill_size.py            # report, exit 0
uv run python ./scripts/validation/skill_size.py --ci       # gate, exit 1 on FAIL
uv run python ./scripts/validation/skill_size.py --path .claude/skills/<name>/SKILL.md
```

- Limits: warn over 300 lines, block over 500. Escape: `size-exception: true` in frontmatter, justification required.
- Current baseline (as of 2026-07-03): 92 skills, 26 warnings, 1 FAIL (`.claude/skills/SkillForge/SKILL.md` at 1033 lines).
- Healthy: your skill lands under 300; overflow goes to `references/` files.
- Unhealthy: a skill creeping from warn toward 500; that is the signal to split before the block gate bites.
- Trap: without `--ci` the script prints FAIL but exits 0. In scripts, pass `--ci` or you will read success where there is none.

### Orphan references

Scans structured artifacts for references to skills, scripts, and counts that do not match the working tree (REQ-009, issue #1939). Default targets: `.agents/specs`, `tests/evals`, `.claude/.claude-plugin/plugin.json`, and both `marketplace.json` files.

```bash
uv run python .claude/skills/orphan-ref-validator/scripts/scan.py            # ADR-056 JSON envelope + VERDICT line
uv run python .claude/skills/orphan-ref-validator/scripts/scan.py --include-adrs
```

- Output contract: JSON envelope then a final `VERDICT: PASS|WARN|CRITICAL_FAIL` line. Exit 0 for PASS/WARN, 1 for CRITICAL_FAIL, 2 for config error.
- Current baseline (as of 2026-07-02): 99 files scanned, 216 refs checked, 49 findings, all severity critical, `VERDICT: CRITICAL_FAIL`, exit 1. The findings sit in historical specs (for example `.agents/specs/requirements/REQ-009-orphan-ref-validator.md:32` referencing skills that no longer exist).
- Healthy delta: your PR adds zero findings. Backticked kebab names in anything you write must resolve to real `.claude/skills/<name>/` directories.
- Unhealthy: new findings pointing at YOUR files; CI runs this on PR-relevant targets and a new critical blocks.
- Suppression, sparingly: line-scope `orphan-ref-ignore` and file-scope `orphan-ref-ignore-file` HTML-comment directives; the file-scope directive must appear in the first 50 lines (`scan.py:157`, `patterns.py:95`).
- Trap: do not "fix" the red baseline by mass-adding ignore directives to historical specs; that destroys the instrument. Measure your delta instead.

### Golden principles

Mechanical enforcement of `.agents/governance/golden-principles.md`: rules `script-language`, `skill-frontmatter`, `agent-definition`, `yaml-logic`, `actions-pinned`.

```bash
uv run python .claude/skills/golden-principles/scripts/scan_principles.py                     # whole repo
uv run python .claude/skills/golden-principles/scripts/scan_principles.py --diff-scope main   # only your changed files
uv run python .claude/skills/golden-principles/scripts/scan_principles.py --rules yaml-logic --format json
```

- Exit codes: 0 clean, 1 script error, 10 violations. 10 is a finding, not a crash.
- Current baseline (as of 2026-07-02): 5990 files scanned, 23 errors, 102 warnings, exit 10. Standing errors include GP-001 shell scripts under `src/copilot-cli/skills/github/scripts/gh-native/`.
- Healthy: `--diff-scope main` clean for your branch.
- Unhealthy: new errors on your changed files; each comes with an `AGENT_REMEDIATION` block telling you the fix.
- Trap: findings in generated trees (`src/copilot-cli/`, `.github/instructions/`) must be fixed at the canonical source under `.claude/` and regenerated, never edited in place. Suppress a true false positive with `# golden-principle: ignore <rule>` on the flagged line.

### Drift gates as measurements

Three separate drift surfaces; run all three when you suspect any generation problem:

| Gate | Command | Current reading (as of 2026-07-02) | Meaning of red |
|---|---|---|---|
| Agents | `uv run python build/generate_agents.py --validate` | `VALIDATION PASSED`, 0.05s, exit 0 | `templates/agents/*.shared.md` and `src/` trees diverged |
| Mirrors | `uv run python build/scripts/build_all.py --check` | exit 0 | A `.claude/` canonical edit was not regenerated, or a generated tree was hand-edited |
| Plugin lib | `uv run python ./scripts/sync_plugin_lib.py --check` | `All plugin lib copies are in sync.`, exit 0 | `scripts/{hook_utilities,github_core,ai_review_common}` and `.claude/lib/` diverged |

- `build_all.py --check` exits 2 on staleness (docstring, `build/scripts/build_all.py:19`). Its log legitimately says `Mode: Generate` mid-run; the snapshot/restore guard (#2440) makes the whole run read-only.
- Trap, the expensive one: drift output shows a DIFFERENCE, not a DIRECTION. On 2025-12-15 an agent "fixed" drift by editing the canonical source to match the stale generated tree (commit reverted). Before fixing any drift red, answer "which side is the source of truth?" via `.agents/governance/GENERATOR-FILES.md`, then see `ai-agents-generation-and-release` for the regeneration workflow.

### Guard telemetry and maturity tiers

Push guards built on `.claude/hooks/PreToolUse/push_guard_base.py` emit one `EVENT={...}` JSON line to stderr per run. Two build scripts consume them: `build/scripts/aggregate_guard_intercepts.py` (reads `.agents/telemetry/` when present, else stdin) and `build/scripts/classify_guard_maturity.py` (assigns tiers). The `guard-maturity` skill wraps both:

```bash
uv run python .claude/skills/guard-maturity/scripts/run_report.py
```

Tier semantics (from `classify_guard_maturity.py`, first match wins): Harmful (3+ intercepts, fitness below -0.02: remove), Proficient (60+ days, 10+ intercepts, fitness at or above +0.02: keep), Mature (30+ days, 5+ intercepts, fitness at or above 0), Inert (30+ days, 0 intercepts: prune candidate), Growing (14+ days, 1+ intercept), Budding (under 14 days). Fitness is `block_rate - 0.5`.

- Current baseline (as of 2026-07-02): 4 guards reported (`manifest-count`, `markdown-lint`, `pr-description`, `session-log-field`), all Budding, 0 intercepts, fitness -0.50, age n/a.
- Honest caveat: `.agents/telemetry/` does not exist in this checkout, so EVENT lines are not being persisted anywhere the aggregator reads by default. The measurement pipeline exists; its production feed is not wired (unverified who or what should populate `.agents/telemetry/`). Treat current tier output as a smoke test of the classifier, not as evidence about guard value.
- Healthy: guards age into Mature/Proficient. Unhealthy: Inert (validator too narrow or guard pointless) or Harmful (normalizes bypass; remove).

### Coverage measurement

```bash
uv run pytest tests/ --cov --cov-report=term
uv run pytest <exact test files> --cov=<module_name> --cov-branch --cov-fail-under=100   # pin form
```

Two traps, both already paid for:

- File-set sensitivity (#1963): a `--cov-fail-under=100` pin is only valid with the exact test-file set it was calibrated with. CI's own comment records that a drifted set "alone now reports 63% and trips --cov-fail-under=100" (`.github/workflows/pytest.yml:144`).
- Module-name form (#2063): use `--cov=scripts.ai_review_common.verdict` style (dotted module), never a file path. The file-path form yields "Module never imported" and 0% coverage on pytest-cov 7.x / Python 3.14 (`pytest.yml:150-152`; live example at `pytest.yml:147`).

The evidence bar (100% block coverage on changed files, pos+neg+edge) belongs to `ai-agents-validation-and-qa`; this section only covers how to get a trustworthy number. Targets: 100% security, 80% business, 60% docs (AGENTS.md Standards).

### Eval harness

Behavioral A/B measurement for prompt and agent changes (ADR-057). Transport is `scripts/eval/_anthropic_api.py` (urllib); the `anthropic` SDK is NOT installed, so custom eval code must import `call_api` from there. `ANTHROPIC_API_KEY` comes from env or `.env`.

```bash
uv run python ./scripts/eval/eval-prompt-change.py --prompt <file> --scenarios <scenarios.json> --dry-run
uv run python ./scripts/eval/eval-agent-vs-baseline.py --agent <name> --fixtures <dir> --dry-run
```

- `--dry-run` validates inputs and prints the plan with zero API spend. It is the ONLY no-spend path; there is no `--mock`. Always run it first.
- Real runs: default 3 runs per scenario, 5 with `--security-critical` (100% pass required). Keep baseline and variant on the same `--provider`; cross-provider scores are not comparable (ADR-058).
- Healthy discipline: predict the delta BEFORE running, then compare. The prediction recipe lives in `ai-agents-empirical-probe-toolkit`.
- Trap: an eval that confirms whatever you hoped is measurement theater. If you did not write down the expected number first, you measured nothing.

### Commit-count monitor

```bash
git rev-list --count HEAD ^origin/main
```

Cap 20 commits per PR, warn above 15 (AGENTS.md Mid gate, ADR-008; enforced by `pr-validation.yml` and the pre-push hook). Current reading on a fresh main checkout: 0. Run it mid-session, not at push time, so you can split the branch while it is still cheap.

## Current Baselines Summary (as of 2026-07-02; description budget and skill size re-measured 2026-07-03)

| Instrument | Reading | State |
|---|---|---|
| Description budget | 92 skills, 35892 chars, ~8973 est. tokens | Green, trend it |
| Skill size | 26 warnings, 1 FAIL (SkillForge, 1033 lines) | Red on main |
| Orphan refs (default targets) | 49 critical findings, CRITICAL_FAIL | Red on main |
| Golden principles | 23 errors, 102 warnings, exit 10 | Red on main |
| Agent drift | VALIDATION PASSED | Green |
| Mirror drift (`build_all.py --check`) | exit 0 | Green |
| Plugin lib drift | in sync | Green |
| Guard maturity | 4 guards, all Budding, 0 intercepts | Feed not wired |
| Commit count | 0 on main | Green |

Re-measure before trusting any of these numbers; they are a snapshot, and the whole point of this skill is that re-measuring costs one command.

## Anti-Patterns

| Anti-pattern | Why it burns you |
|---|---|
| Eyeballing ("the diff looks fine") instead of running the instrument | The 2025-12-15 drift inversion and PR #1887's 0/35 prevented-fix audit both started with confident eyeballs |
| Treating a red baseline as your failure, or silently "fixing" it repo-wide | Mass edits outside your scope; PR #908's scoped-lint lesson. Flag it, keep your delta clean |
| Quoting the chars/4 token estimate as an exact cost | It is a trend instrument, by design |
| Reading `Mode: Generate` in `--check` output as proof the gate wrote files | #2440 snapshot/restore makes it read-only; check `git status --porcelain` |
| Fixing scanner findings inside generated trees | Regenerated over on the next build; fix the `.claude/` canonical source |
| `--cov=<file path>` or an uncalibrated `--cov-fail-under` pin | 0% "Module never imported" (#2063) or a 63% false trip (#1963) |
| Running a paid eval without `--dry-run` and a written prediction first | Spend with no falsifiable claim; see `ai-agents-research-methodology` |
| Adding a detector or threshold without replaying it against recent real PRs | #1989 M4 shipped a threshold of 6 in a repo whose max was 4; it could never fire |

## Verification

Before citing any number from this toolkit in a PR, session log, or decision:

- [ ] The command was run from repo root with `uv run python` and the exit code was captured, not just the prose output.
- [ ] The reading was compared against the Current Baselines Summary, and what you report is the DELTA your change introduces.
- [ ] Any red you did not cause is flagged in your PR description, not silently fixed or silently ignored.
- [ ] Volatile numbers you quote are date-stamped, the way this file stamps its own.

## Provenance and Maintenance

Written 2026-07-02. All baselines measured by running the instruments on this checkout on that date. Retro-cited short SHAs do not resolve locally even with full history present (~1471 commits as of 2026-07-03); do not use `git log` to re-derive any of this.

Sources: `scripts/skill_description_budget.py` (docstring, issue #2794), `scripts/validation/skill_size.py` (limits, issue #676), `.claude/skills/orphan-ref-validator/scripts/scan.py:157` and `patterns.py:95-96` (directives), `.claude/skills/golden-principles/scripts/scan_principles.py` (rules, exit 10), `build/scripts/build_all.py:19,893` (#2440 read-only check), `build/scripts/classify_guard_maturity.py` (tier table), `build/scripts/aggregate_guard_intercepts.py:185-189` (telemetry default source), `.github/workflows/pytest.yml:144-164` (coverage pins), `scripts/eval/eval-prompt-change.py --help` and `scripts/eval/_anthropic_api.py` (harness), `AGENTS.md:19` (commit cap), `.claude/skills/SkillForge/scripts/validate-skill.py:171` (1024 cap).

Re-verify one-liners for every volatile fact:

| Fact | Re-verify with |
|---|---|
| Description budget totals | `uv run python ./scripts/skill_description_budget.py` |
| Skill size FAIL list | `uv run python ./scripts/validation/skill_size.py` |
| Orphan-ref verdict and counts | `uv run python .claude/skills/orphan-ref-validator/scripts/scan.py` (read last line) |
| Golden-principles totals | `uv run python .claude/skills/golden-principles/scripts/scan_principles.py` (read last line, expect exit 10 while baseline is red) |
| Drift gates green | run all three gate commands in the drift table |
| Guard tiers and telemetry dir | `uv run python .claude/skills/guard-maturity/scripts/run_report.py` and `ls .agents/telemetry/` |
| push_guard_base location | `ls .claude/hooks/PreToolUse/push_guard_base.py` |
| Coverage pin forms | `grep -n "cov-fail-under" .github/workflows/pytest.yml` |
| Commit count | `git rev-list --count HEAD ^origin/main` |

When a baseline here goes stale (a red turns green or a number moves), update the table in the same PR that moved it, or file an issue pointing at this file.
