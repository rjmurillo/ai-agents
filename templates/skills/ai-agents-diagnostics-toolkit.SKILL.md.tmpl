---
name: ai-agents-diagnostics-toolkit
version: 1.0.0
license: MIT
description: Catalog of this repo's measurement instruments, each with command, current baseline, and interpretation guide. Covers skill size and description budgets, orphan-ref and golden-principles scans, drift gates as signals, coverage pins, and the eval harness. Use when you say `measure this`, `read the drift signal`, `check skill budgets`. Do NOT use to fix what you measure (use `ai-agents-debugging-playbook`) or for evidence standards (use `ai-agents-validation-and-qa`).
metadata:
  distribution: repo-local
  routing:
    role: conditional-adjunct
    invoker: ai-agents-debugging-playbook
    trigger: ai-agents-debugging-playbook points here to measure drift, budgets, or telemetry as a number
    user-facing: false
---

# ai-agents Diagnostics Toolkit

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths because its audience is repo contributors, not plugin consumers. Declared paths: .claude/skills/skillforge/scripts/_constants.py, build/audit/GENERATION-AUDIT.md, build/generate_agents.py, build/scripts/build_all.py, scripts/baseline_snapshot.py, scripts/eval/_anthropic_api.py, scripts/eval/eval-agent-vs-baseline.py, scripts/eval/eval-prompt-change.py, scripts/instruments.py, scripts/skill_description_budget.py, scripts/validation/run_install_parity_ci.py, scripts/validation/skill_size.py, src/claude/skills/golden-principles/scripts/scan_principles.py, src/claude/skills/orphan-ref-validator/scripts/scan.py -->
Measure instead of eyeball. Every instrument below leaves the trees it measures unchanged, turning a vague worry ("are skills getting bloated?", "did generation drift?") into a number you can compare against a baseline; `build_all.py --check`'s one exception, a gitignored audit file outside those trees, is covered below. The Instrument Index gives you, per instrument, the question it answers and the exact command; [`references/instrument-guides.md`](references/instrument-guides.md) gives the healthy and unhealthy reading, the baseline, and the trap that has already cost someone time.

Vocabulary, defined once: an "instrument" is a script whose output you read, not a gate you must pass. A "drift gate" is a CI check that fails when a generated tree stops matching its canonical source. A "baseline" is the number the instrument reports on a clean checkout of main; you measure your delta against it.

## Triggers

- `measure this`
- `read the drift signal`
- `check skill budgets`
- `interpret this scan output`

## Instrument Index

| Instrument | Question it answers | Command (from repo root) |
|---|---|---|
| Description budget | How much standing context do skill descriptions cost? | `uv run python ./scripts/skill_description_budget.py` |
| Skill size | Which SKILL.md files exceed the 300-warn / 500-block line limits or the 24576-byte limit? | `uv run python ./scripts/validation/skill_size.py` |
| Orphan refs | Do specs, evals, and manifests reference entities that no longer exist? | `python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/orphan-ref-validator/scripts/scan.py"` |
| Golden principles | Where does the repo violate the mechanical rules (GP-001, GP-003, GP-004, GP-005, GP-006)? | `python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/golden-principles/scripts/scan_principles.py"` |
| Agent drift | Do generated agent files match their templates? | `uv run python build/generate_agents.py --validate` |
| Mirror and lib drift | Do the generated mirror and lib trees match their canonical sources? | `uv run python build/scripts/build_all.py --check` |
| Install parity | Does the install surface stay in parity across hosts (ADR-035)? | `uv run python scripts/validation/run_install_parity_ci.py` |
| Coverage | Is changed code actually exercised by tests? | `uv run pytest <tests> --cov=<module> --cov-branch` |
| Eval A/B | Did a prompt or agent change alter behavior, measurably? | `uv run python ./scripts/eval/eval-prompt-change.py --scenarios <file> --dry-run` |
| Eval agent vs baseline | Does an agent beat the baseline on fixtures? | `uv run python ./scripts/eval/eval-agent-vs-baseline.py --agent <name> --fixtures <dir> --dry-run` |
| Commit count | Advisory-only signal, not a cap | `git rev-list --count HEAD ^origin/main` |

To list or run any row with an existence check, use `python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/ai-agents-diagnostics-toolkit/scripts/instruments.py" --repo . list`. It prints each row with `exists: true|false` and exits 1 on a missing file. `run <id> -- <args>` execs the row and passes its exit code through. It does not judge a reading; the guides do.

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
- Every instrument here leaves the owned trees it reads unchanged in the modes shown, `build_all.py --check` included, but that one is not a no-write run overall: it runs its generators and then restores the owned trees from a snapshot (`_snapshot_owned_prefixes` and `_restore_owned_prefixes` in `build/scripts/build_all.py`), so its log prints `Mode: Generate` and a nonzero `Written:` count even though the owned trees end the run as they started, and separately `write_audit` creates or overwrites `build/audit/GENERATION-AUDIT.md` on every invocation, a path outside the snapshot that restore never touches. That file is gitignored (`/build/audit/`) and untracked, so it exists only after a build run. That is why `git status --porcelain` still comes back clean over the owned trees. Confirm with `git status --porcelain` if suspicious, and see the trap in the Drift gates section of [`references/instrument-guides.md`](references/instrument-guides.md).
- Read the exit code, not just the prose. It is the machine signal:

| Exit code | Convention (ADR-035 / AGENTS.md) | Exceptions |
|---|---|---|
| 0 | Healthy or within limits | `skill_size.py` prints FAIL lines but exits 0 unless `--ci` |
| 1 | Logic finding (budget exceeded, CRITICAL_FAIL, over limit in `--ci`) | |
| 2 | Config error (bad path, bad args); for `build_all.py --check`, staleness, a path under `OWNED_PREFIXES` that cannot be read or redirects (symlink or junction) or holds a nested git repository, or a generator writing under `.claude/` (REQ-003-010). Read stderr: only the staleness producer is fixed by regenerating | |
| 3 | External failure; for `build_all.py --check`, git state unreadable (launch failure, timeout, nonzero exit), not fixed by regenerating | |
| 10 | Violations found | `scan_principles.py` only |

### Phase 3: Read the number against the baseline

Get the numbers with the snapshot script, then compare them with the guides in [`references/instrument-guides.md`](references/instrument-guides.md):

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/ai-agents-diagnostics-toolkit/scripts/baseline_snapshot.py" --repo .
```

It runs the description budget, skill size, orphan-ref, and golden-principles instruments and prints their headline counts as JSON with the HEAD SHA and date. It never runs `build_all.py --check`, so drift gates and eval results need their own commands. Exit 1 means an instrument's output was unreadable; exit 3 means git or an instrument failed to start.

Golden principles is red on main (exit 10). The enforced description gate is `.github/workflows/skill-passive-compliance.yml`, which runs `scripts/skill_description_budget.py --budget-file scripts/skill_description_budget.json` against a per-root char ceiling. Read the current counts with `instruments.py run baseline-snapshot`. What matters for your change is the delta: your PR should add zero new findings, and should not grow a budget without saying so.

### Phase 4: Act on the reading

Green and unchanged: move on. Red where the baseline was green: your change caused it; triage via `ai-agents-debugging-playbook`. Red where the baseline was already red: not yours to fix silently, but flag it (see-something-say-something) and keep your delta clean.

## Instrument Guides

Per-instrument detail (the exact command variants, the baseline snapshot, the healthy and unhealthy readings, and the trap each instrument has already cost someone) lives in [`references/instrument-guides.md`](references/instrument-guides.md). Pick the instrument from the index above, then consult its section.

## Anti-Patterns

| Anti-pattern | Why it burns you |
|---|---|
| Eyeballing ("the diff looks fine") instead of running the instrument | The 2025-12-15 drift inversion and an earlier 0/35 prevented-fix audit both started with confident eyeballs |
| Treating a red baseline as your failure, or silently "fixing" it repo-wide | Mass edits outside your scope; the scoped-lint lesson. Flag it, keep your delta clean |
| Quoting the chars/4 token estimate as an exact cost | It is a trend instrument, by design |
| Reading `Mode: Generate` in `--check` output as proof the gate wrote files | The snapshot/restore makes it read-only; check `git status --porcelain` |
| Fixing scanner findings inside generated trees | Regenerated over on the next build; fix the `.claude/` canonical source |
| `--cov=<file path>` or an uncalibrated `--cov-fail-under` pin | 0% "Module never imported" or a 63% false trip |
| Running a paid eval without `--dry-run` and a written prediction first | Spend with no falsifiable claim; see `ai-agents-research-methodology` |
| Adding a detector or threshold without replaying it against recent real PRs | An earlier M4 shipped a threshold of 6 in a repo whose max was 4; it could never fire |

## Scripts

| Script | Purpose |
|---|---|
| `scripts/instruments.py` | List every instrument row with an existence check, or run one by id |
| `scripts/baseline_snapshot.py` | Print the headline numbers of the four read-only instruments as JSON |

Both are read-only and answer `--help`. Exit codes: 0 ok, 1 a finding (missing instrument file, unreadable output), 2 bad arguments, 3 external failure.

## Verification

Before citing any number from this toolkit in a PR, session log, or decision:

- [ ] The command was run from repo root with `uv run python` and the exit code was captured, not just the prose output.
- [ ] The reading was compared against a fresh `baseline_snapshot.py` run and the guides in [`references/instrument-guides.md`](references/instrument-guides.md), and what you report is the DELTA your change introduces.
- [ ] Any red you did not cause is flagged in your PR description, not silently fixed or silently ignored.
- [ ] Volatile numbers you quote are date-stamped, the way this file stamps its own.

## Provenance and Maintenance

Checks live in `reverify.json`. Run the drift command after any edit:

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/skill-bootstrap/scripts/bootstrap_drift.py" check --repo . --skills-root .claude/skills --name ai-agents-diagnostics-toolkit --require
```

Sources: `scripts/skill_description_budget.py` (docstring), `scripts/validation/skill_size.py` (limits), `src/claude/skills/orphan-ref-validator/scripts/scan.py` (`DEFAULT_TARGETS`, directives), `src/claude/skills/golden-principles/scripts/scan_principles.py` (rules, exit 10 while baseline is red), `build/scripts/build_all.py` (`write_audit`, the `EXIT CODES` docstring), `.github/workflows/pytest.yml` (REQ-009 coverage steps), `scripts/eval/eval-prompt-change.py --help`, `scripts/eval/_anthropic_api.py` (harness), `.claude/skills/skillforge/scripts/_constants.py` (`DESCRIPTION_MAX_LENGTH`, the 1024 cap).

Facts that go stale:

| Fact | Re-verify with |
|---|---|
| Any baseline number | `baseline_snapshot.py` above |
| Drift gates green | the three gate commands in the Drift gates section of [`references/instrument-guides.md`](references/instrument-guides.md) |
| Push guards and guard-maturity classifier removed under ADR-084 | `ls .claude/hooks/PreToolUse/` (no `push_guard_base.py` or `invoke_*_guard.py`) and `ls -d .claude/skills/guard-maturity` (expect "No such file or directory") |
| Coverage pin forms | `grep -n "cov-fail-under" .github/workflows/pytest.yml` |

When a baseline here goes stale, rerun the snapshot and update the dated line in the same PR that moved it.
