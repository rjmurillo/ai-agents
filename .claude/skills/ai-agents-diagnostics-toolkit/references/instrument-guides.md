# Diagnostics Instrument Guides

Per-instrument detail for `ai-agents-diagnostics-toolkit`: the exact commands, the current repo baseline (as of 2026-07-29), the healthy and unhealthy readings, and the trap each instrument has already cost someone. The SKILL.md Instrument Index routes you here; consult the matching section when you run an instrument.

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->

## Instrument Guides

### Description budget

Every skill description is resident in context on every turn, before any work begins. This instrument sums them (issue #2794).

```bash
uv run python ./scripts/skill_description_budget.py --top 10
uv run python ./scripts/skill_description_budget.py --output-format json
uv run python ./scripts/skill_description_budget.py --max-total-tokens 8000   # gate mode, exit 1 over budget
```

- Current baseline (as of 2026-07-29): 98 skills, 40940 chars, ~10235 estimated tokens; top offenders `adr-generator` at 830 chars and `software-engineering-library` at 824 chars.
- Healthy: total flat or falling; a new skill adds roughly 350-500 chars (house style), hard cap 1024 (`DESCRIPTION_MAX_LENGTH = 1024` at `.claude/skills/skillforge/scripts/_constants.py:65`, enforced at `.claude/skills/skillforge/scripts/validate-skill.py:241-242`). The copy at `validate-skill.py:185` is an `except ImportError` fallback, so change the constants file, not the validator.
- Unhealthy: total climbing PR over PR with no budget flag set; any single description near 1024.
- Trap: the token figure is a chars/4 heuristic, deliberately not tiktoken. Trend it; never quote it as an exact cost.

### Skill size

```bash
uv run python ./scripts/validation/skill_size.py            # report, exit 0
uv run python ./scripts/validation/skill_size.py --ci       # gate, exit 1 on FAIL
uv run python ./scripts/validation/skill_size.py --path .claude/skills/<name>/SKILL.md
```

- Limits: warn over 300 lines, block over 500. Escape: `size-exception: true` in frontmatter, justification required.
- Current baseline (as of 2026-07-29): 98 skills, 44 warnings, 0 failures, exit 0. `.claude/skills/skillforge/SKILL.md` is now 298 lines and only warns.
- Healthy: your skill lands under 300; overflow goes to `references/` files.
- Unhealthy: a skill creeping from warn toward 500; that is the signal to split before the block gate bites.
- Trap: without `--ci` the script prints FAIL but exits 0. In scripts, pass `--ci` or you will read success where there is none.

### Orphan references

Scans structured artifacts for references to skills, scripts, and counts that do not match the working tree (REQ-009, issue #1939). Default targets: `.agents/specs`, `tests/evals`, `.claude/.claude-plugin/plugin.json`, and both `marketplace.json` files.

```bash
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/orphan-ref-validator/scripts/scan.py"            # ADR-056 JSON envelope + VERDICT line
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/orphan-ref-validator/scripts/scan.py" --include-adrs
```

- Output contract: JSON envelope then a final `VERDICT: PASS|WARN|CRITICAL_FAIL` line. Exit 0 for PASS/WARN, 1 for CRITICAL_FAIL, 2 for config error.
- Current baseline (as of 2026-07-29): 190 files scanned, 535 refs checked, 0 findings, `VERDICT: PASS`, exit 0. The instrument reads green only because 187 refs are directive-suppressed: the historical specs that once produced findings now carry `orphan-ref-ignore` markers, so read the suppression count alongside the verdict.
- Healthy delta: your PR adds zero findings. Backticked kebab names in anything you write must resolve to real `.claude/skills/<name>/` directories.
- Unhealthy: new findings pointing at YOUR files; CI runs this on PR-relevant targets and a new critical blocks.
- Suppression, sparingly: line-scope `orphan-ref-ignore` and file-scope `orphan-ref-ignore-file` HTML-comment directives; the file-scope directive must appear in the first 50 lines (`scan.py:234-235`, `patterns.py:89`).
- Trap: do not "fix" the red baseline by mass-adding ignore directives to historical specs; that destroys the instrument. Measure your delta instead.

### Golden principles

Mechanical enforcement of `.agents/governance/golden-principles.md`: rules `script-language`, `skill-frontmatter`, `agent-definition`, `yaml-logic`, `actions-pinned`.

```bash
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/golden-principles/scripts/scan_principles.py"                     # whole repo
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/golden-principles/scripts/scan_principles.py" --diff-scope main   # only your changed files
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/golden-principles/scripts/scan_principles.py" --rules yaml-logic --format json
```

- Exit codes: 0 clean, 1 script error, 10 violations. 10 is a finding, not a crash.
- Current baseline (as of 2026-07-29): 7912 files scanned, 109 errors, 92 warnings, exit 10. Errors break down as GP-003 `skill-frontmatter` 89, GP-001 `script-language` 16, GP-004 `agent-definition` 4. The GP-001 set is still the shell scripts under `src/copilot-cli/skills/github/scripts/gh-native/`. All 92 warnings are GP-005 `yaml-logic`. The file count tracks repo size and moves with every merge, so trend the error and warning counts; treat a changed file count alone as noise.
- Healthy: `--diff-scope main` clean for your branch.
- Unhealthy: new errors on your changed files; each comes with an `AGENT_REMEDIATION` block telling you the fix.
- Trap: findings in generated trees (`src/copilot-cli/`, `.github/instructions/`) must be fixed at the canonical source under `.claude/` and regenerated, never edited in place. Suppress a true false positive with `# golden-principle: ignore <rule>` on the flagged line.

### Drift gates as measurements

Three separate drift surfaces; run all three when you suspect any generation problem:

| Gate | Command | Current reading (as of 2026-07-29) | Meaning of red |
|---|---|---|---|
| Agents | `uv run python build/generate_agents.py --validate` | `VALIDATION PASSED`, 0.05s, exit 0 | `templates/agents/*.shared.md` and `src/` trees diverged |
| Mirrors | `uv run python build/scripts/build_all.py --check` | exit 0 | A `.claude/` canonical edit was not regenerated, or a generated tree was hand-edited |
| Plugin lib | `uv run python ./scripts/sync_plugin_lib.py --check` | `All plugin lib copies are in sync.`, exit 0 | `scripts/{hook_utilities,github_core,ai_review_common}` and `.claude/lib/` diverged |

- `build_all.py --check` exits 2 on staleness (docstring, `build/scripts/build_all.py:19`). Its log legitimately says `Mode: Generate` mid-run; the snapshot/restore guard (#2440) makes the whole run read-only.
- Trap, the expensive one: drift output shows a DIFFERENCE, not a DIRECTION. On 2025-12-15 an agent "fixed" drift by editing the canonical source to match the stale generated tree (commit reverted). Before fixing any drift red, answer "which side is the source of truth?" via `.agents/governance/GENERATOR-FILES.md`, then see `ai-agents-generation-and-release` for the regeneration workflow.

### Guard telemetry and maturity tiers (retired)

RETIRED, not just as an instrument but entirely: issue #5154 deleted
`push_guard_base.py` and every push guard built on it, so nothing emits the
`EVENT={...}` stderr line any more, and in the same change it deleted the
now-producer-less classifier skill and its two build scripts (an
aggregator and a classifier) rather than leave them measuring nothing.
Tier semantics (Harmful, Proficient, Mature, Inert, Growing,
Budding, keyed on age/intercepts/fitness) are documented for historical
reference in `.agents/retrospective/` entries that cite this instrument; there
is no live command to run. A future guard that adopts the same `EVENT=`
stderr schema would need to rebuild both the aggregator and the classifier
from scratch. Re-verify the removal: `ls .claude/hooks/PreToolUse/` (expect
no `push_guard_base.py` or `invoke_*_guard.py`) and
`ls .claude/skills/ | grep guard-maturity` (expect no output).

### Coverage measurement

```bash
uv run pytest tests/ --cov --cov-report=term
uv run pytest <exact test files> --cov=<module_name> --cov-branch --cov-fail-under=100   # pin form
```

Two traps, both already paid for:

- File-set sensitivity (#1963): a `--cov-fail-under=100` pin is only valid with the exact test-file set it was calibrated with. CI's own comment records that a drifted set "alone now reports 63% and trips --cov-fail-under=100" (`.github/workflows/pytest.yml:202`).
- Module-name form (#2063): use `--cov=scripts.ai_review_common.verdict` style (dotted module), never a file path. The file-path form yields "Module never imported" and 0% coverage on pytest-cov 7.x / Python 3.14 (`pytest.yml:209`; live example at `pytest.yml:205`).

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

Advisory only, never blocking: `needs-split` label at 10 commits, WARNING notice at 10, ALERT notice at 15 (AGENTS.md Mid gate, advisory only per ADR-099; the notice is surfaced by `pr-validation.yml` and the pre-push hook; thresholds in `scripts/validation/pr_commit_count.py`). Current reading on a fresh main checkout: 0. Run it mid-session, not at push time, so you can split the branch while it is still cheap.

## Current Baselines Summary (as of 2026-07-29)

| Instrument | Reading | State |
|---|---|---|
| Description budget | 98 skills, 40940 chars, ~10235 est. tokens | Red in gate mode: over the 8000 budget, exit 1 |
| Skill size | 98 skills, 44 warnings, 0 failures, exit 0 | Green |
| Orphan refs (default targets) | 190 files, 535 refs, 0 findings, `VERDICT: PASS`, exit 0 | Green, but 187 refs are directive-suppressed |
| Golden principles | 7912 files, 109 errors, 92 warnings, exit 10 | Red on main |
| Agent drift | `VALIDATION PASSED`, exit 0 | Green |
| Mirror drift (`build_all.py --check`) | exit 0 | Green |
| Plugin lib drift | `All plugin lib copies are in sync.`, exit 0 | Green |
| Commit count | 0 on main | Green |

Two instruments read red on main: golden principles (exit 10) and the description budget in gate mode (exit 1). Guard telemetry and maturity tiers is no longer in this list: it was retired entirely under ADR-084 (issue #5154), not merely feed-starved. Every other instrument is green.

Re-measure before trusting any of these numbers; they are a snapshot, and the whole point of this skill is that re-measuring costs one command.
