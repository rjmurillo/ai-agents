---
name: ai-agents-diagnostics-toolkit
version: 1.0.0
license: MIT
description: Catalog of this repo's measurement instruments, each with command, current baseline, and interpretation guide. Covers skill size and description budgets, orphan-ref and golden-principles scans, drift gates as signals, guard telemetry and maturity tiers, coverage pins, and the eval harness. Use when you say `measure this`, `read the drift signal`, `check skill budgets`, `guard maturity report`. Do NOT use to fix what you measure (use `ai-agents-debugging-playbook`) or for evidence standards (use `ai-agents-validation-and-qa`).
---

# ai-agents Diagnostics Toolkit

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->
Measure instead of eyeball. Every instrument below is a read-only command that turns a vague worry ("are skills getting bloated?", "did generation drift?") into a number you can compare against a baseline. The Instrument Index gives you, per instrument, the question it answers and the exact command; [`references/instrument-guides.md`](references/instrument-guides.md) gives the healthy and unhealthy reading, the current repo baseline (as of 2026-07-29), and the trap that has already cost someone time.

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
| Orphan refs | Do specs, evals, and manifests reference entities that no longer exist? | `uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/orphan-ref-validator/scripts/scan.py"` |
| Golden principles | Where does the repo violate GP-001..GP-005 mechanical rules? | `uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/golden-principles/scripts/scan_principles.py"` |
| Agent drift | Do generated agent files match their templates? | `uv run python build/generate_agents.py --validate` |
| Mirror drift | Do the 7 generated mirror trees match `.claude/` canonical sources? | `uv run python build/scripts/build_all.py --check` |
| Lib drift | Do `.claude/lib/` copies match `scripts/` canonical modules? | `uv run python ./scripts/sync_plugin_lib.py --check` |
| Guard maturity | Which push guards earn their keep? | `uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/guard-maturity/scripts/run_report.py"` |
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
- All instruments here are read-only in the modes shown. `build_all.py --check` runs its generators and then restores the owned trees from a snapshot (issue #2440, `build/scripts/build_all.py:1005-1033`), so its log prints `Mode: Generate` and a nonzero `Written:` count even though nothing changes on disk. Confirm with `git status --porcelain` if suspicious, and see the trap in the Drift gates section of [`references/instrument-guides.md`](references/instrument-guides.md).
- Read the exit code, not just the prose. It is the machine signal:

| Exit code | Convention (ADR-035 / AGENTS.md) | Exceptions |
|---|---|---|
| 0 | Healthy or within limits | `skill_size.py` prints FAIL lines but exits 0 unless `--ci` |
| 1 | Logic finding (budget exceeded, CRITICAL_FAIL, over limit in `--ci`) | |
| 2 | Config error (bad path, bad args) or staleness for `build_all.py --check` | |
| 10 | Violations found | `scan_principles.py` only |

### Phase 3: Read the number against the baseline

Compare against the "Current baseline" entry in each guide in [`references/instrument-guides.md`](references/instrument-guides.md). The repo baseline is NOT all green: golden principles is red on main today (exit 10, 109 errors), and the description budget is over its 8000-token gate at ~10235 (exit 1 in gate mode). What matters for your change is the delta: your PR should add zero new findings, and should not grow a budget without saying so.

### Phase 4: Act on the reading

Green and unchanged: move on. Red where the baseline was green: your change caused it; triage via `ai-agents-debugging-playbook`. Red where the baseline was already red: not yours to fix silently, but flag it (see-something-say-something) and keep your delta clean.

## Instrument Guides

Per-instrument detail (the exact command variants, the current repo baseline as of 2026-07-29, the healthy and unhealthy readings, and the trap each instrument has already cost someone) lives in [`references/instrument-guides.md`](references/instrument-guides.md). Pick the instrument from the index above, then consult its section. That reference also carries the Current Baselines Summary snapshot.

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
- [ ] The reading was compared against the baselines in [`references/instrument-guides.md`](references/instrument-guides.md), and what you report is the DELTA your change introduces.
- [ ] Any red you did not cause is flagged in your PR description, not silently fixed or silently ignored.
- [ ] Volatile numbers you quote are date-stamped, the way this file stamps its own.

## Provenance and Maintenance

Written 2026-07-02; every baseline in this skill re-measured 2026-07-29 by running each instrument on this checkout. Under the current squash-only policy, PR-branch SHAs do not land on `main`. One merge commit predates that policy (`0f13c85ab`, PR #1, 2025-12-13), so verify ancestry instead of assuming. Do not use `git log` to re-derive any of this.

Sources: `scripts/skill_description_budget.py` (docstring, issue #2794), `scripts/validation/skill_size.py` (limits, issue #676), `.claude/skills/orphan-ref-validator/scripts/scan.py:234-235` and `patterns.py:63,89` (directives), `.claude/skills/golden-principles/scripts/scan_principles.py` (rules, exit 10), `build/scripts/build_all.py:19,1005-1033` (#2440 read-only check), `build/scripts/classify_guard_maturity.py` (tier table), `build/scripts/aggregate_guard_intercepts.py:185-189` (telemetry default source), `.github/workflows/pytest.yml:202-222` (coverage pins), `scripts/eval/eval-prompt-change.py --help` and `scripts/eval/_anthropic_api.py` (harness), `AGENTS.md:17` (commit cap), `.claude/skills/skillforge/scripts/_constants.py:65` (1024 cap, canonical; `validate-skill.py:241-242` enforces it).

Re-verify one-liners for every volatile fact:

| Fact | Re-verify with |
|---|---|
| Description budget totals | `uv run python ./scripts/skill_description_budget.py` |
| Skill size FAIL list | `uv run python ./scripts/validation/skill_size.py` |
| Orphan-ref verdict and counts | `uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/orphan-ref-validator/scripts/scan.py"` (read last line) |
| Golden-principles totals | `uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/golden-principles/scripts/scan_principles.py"` (read last line, expect exit 10 while baseline is red) |
| Drift gates green | run all three gate commands from the Drift gates section of [`references/instrument-guides.md`](references/instrument-guides.md) |
| Guard tiers and telemetry dir | `uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/guard-maturity/scripts/run_report.py"` and `ls .agents/telemetry/` |
| push_guard_base location | `ls .claude/hooks/PreToolUse/push_guard_base.py` |
| Coverage pin forms | `grep -n "cov-fail-under" .github/workflows/pytest.yml` |
| Commit count | `git rev-list --count HEAD ^origin/main` |

When a baseline here goes stale (a red turns green or a number moves), update the table in the same PR that moved it, or file an issue pointing at this file.
