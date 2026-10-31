# Diagnostics Instrument Guides

Per-instrument detail for `ai-agents-diagnostics-toolkit`: the exact commands, the current repo baseline (see the snapshot line at the end), the healthy and unhealthy readings, and the trap each instrument has already cost someone. The SKILL.md Instrument Index routes you here; consult the matching section when you run an instrument.

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths because its audience is repo contributors, not plugin consumers (issue #2050). Declared paths: .agents/governance/GENERATOR-FILES.md, .agents/governance/golden-principles.md, .claude/skills/skillforge/scripts/_constants.py, .claude/skills/skillforge/scripts/validate-skill.py, .project-toolkit/retrospective, build/audit/GENERATION-AUDIT.md, build/generate_agents.py, build/scripts/build_all.py, scripts/eval/_anthropic_api.py, scripts/skill_description_budget.json, scripts/validation, templates/agents -->

## Instrument Guides

### Description budget

Every skill description is resident in context on every turn, before any work begins. This instrument sums them (issue #2794).

```bash
uv run python ./scripts/skill_description_budget.py --top 10
uv run python ./scripts/skill_description_budget.py --output-format json
uv run python ./scripts/skill_description_budget.py --budget-file scripts/skill_description_budget.json   # CI gate (skill-passive-compliance.yml), exit 1 over the per-root char ceiling
```

- Current baseline (2026-10-31 at 42e409325): 121 skills, 49257 chars, ~12315 estimated tokens, passing the 49300-char `.claude/skills` ceiling in `scripts/skill_description_budget.json`; top offenders `adr-generator` at 839 chars, `skillforge` at 706, `planner` at 678. Re-measure with `baseline_snapshot.py`.
- Healthy: total flat or falling; a new skill adds roughly 350-500 chars (house style), hard cap 1024 (`DESCRIPTION_MAX_LENGTH = 1024` at `.claude/skills/skillforge/scripts/_constants.py:74`, enforced at `.claude/skills/skillforge/scripts/validate-skill.py:286-287`). The copy at `validate-skill.py:221` (import at `:193`) is an `except ImportError` fallback, so change the constants file, not the validator.
- Unhealthy: total climbing PR over PR with no budget flag set; any single description near 1024.
- Trap: the token figure is a chars/4 heuristic, deliberately not tiktoken. Trend it; never quote it as an exact cost.

### Skill size

```bash
uv run python ./scripts/validation/skill_size.py            # report, exit 0
uv run python ./scripts/validation/skill_size.py --ci       # gate, exit 1 on FAIL
uv run python ./scripts/validation/skill_size.py --path .claude/skills/<name>/SKILL.md
```

- Limits: warn over 300 lines, block over 500, byte limit 24576 (`SKILL_BYTE_LIMIT`), byte target 20480 (`SKILL_BYTE_TARGET`). Escape: `size-exception: true` in frontmatter, justification required.
- Current baseline: run `baseline_snapshot.py` (counts move with every merge). Exit 0, 0 failures. `src/claude/skills/skillforge/SKILL.md` (reached through the `.claude/skills/skillforge` symlink) is 365 lines, over the 300 warn line and under the 500 block line.
- Healthy: your skill lands under 300; overflow goes to `references/` files.
- Unhealthy: a skill creeping from warn toward 500; that is the signal to split before the block gate bites.
- Trap: without `--ci` the script prints FAIL but exits 0. In scripts, pass `--ci` or you will read success where there is none.

### Orphan references

Scans structured artifacts for references to skills, scripts, and counts that do not match the working tree (REQ-009, issue #1939). Default targets (`DEFAULT_TARGETS` in `scan.py`): `.project-toolkit/specs`, `tests`, `src/claude/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, and `.github/plugin/marketplace.json`.

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/orphan-ref-validator/scripts/scan.py"            # ADR-056 JSON envelope + VERDICT line
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/orphan-ref-validator/scripts/scan.py" --include-adrs
```

- Output contract: JSON envelope then a final `VERDICT: PASS|WARN|CRITICAL_FAIL` line. Exit 0 for PASS/WARN, 1 for CRITICAL_FAIL, 2 for config error.
- Current baseline (2026-10-31 at 42e409325): 492 files scanned, 1538 refs checked, 0 findings, `VERDICT: PASS`, exit 0, 316 refs directive-suppressed. The instrument reads green because suppression carries the load: historical specs carry `orphan-ref-ignore` markers, so read the suppression count alongside the verdict. Issue #5581 cleared 44 findings, every one by directive rather than by correcting a reference. A line-scope directive silences every reference on its line, so expect suppressed counts to exceed the findings you meant to clear.
- Treat a rising suppression count as the number to challenge in review.
- Healthy delta: your PR adds zero findings. Backticked kebab names in anything you write must resolve to real `.claude/skills/<name>/` directories.
- Unhealthy: new findings pointing at YOUR files; CI runs this on PR-relevant targets and a new critical blocks.
- Suppression, sparingly: line-scope `orphan-ref-ignore` and file-scope `orphan-ref-ignore-file` HTML-comment directives; the file-scope directive must appear in the first 50 lines (`text.splitlines()[:50]` checked against `FILE_IGNORE_DIRECTIVE_RE` in `scan.py`; the patterns live in `patterns.py`).
- Trap: do not "fix" the red baseline by mass-adding ignore directives to historical specs; that destroys the instrument. Measure your delta instead. The one sanctioned exception, exercised in issue #5581, is narrow: a dated record in the specs tree whose target entity is verifiably gone from the whole tree, suppressed one line at a time, each with its reason in the commit body, never with a file-scope or directory-scope directive. Judged per finding it is outcome 1 of three; applied in bulk to make a count go green it is the trap. If a pass clears most findings by directive, say so with the count where a reviewer will see it, so the choice is reviewed rather than absorbed.

### Golden principles

Mechanical enforcement of `.agents/governance/golden-principles.md`: rules `script-language`, `skill-frontmatter`, `agent-definition`, `yaml-logic`, `actions-pinned`.

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/golden-principles/scripts/scan_principles.py"                     # whole repo
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/golden-principles/scripts/scan_principles.py" --diff-scope main   # only your changed files
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/golden-principles/scripts/scan_principles.py" --rules yaml-logic --format json
```

- Exit codes: 0 clean, 1 script error, 10 violations. 10 is a finding, not a crash.
- Current baseline (2026-10-31 at 42e409325): 13872 files scanned, 7 errors, 74 warnings, exit 10. The per-rule split was not re-measured. The file count tracks repo size and moves with every merge, so trend the error and warning counts; treat a changed file count alone as noise.
- Healthy: `--diff-scope main` clean for your branch.
- Unhealthy: new errors on your changed files; each comes with an `AGENT_REMEDIATION` block telling you the fix.
- Trap: findings in generated trees (`src/copilot-cli/`, `.github/instructions/`) must be fixed at the canonical source under `.claude/` and regenerated, never edited in place. Suppress a true false positive with `# golden-principle: ignore <rule>` on the flagged line.

### Drift gates as measurements

Three separate drift surfaces; run all three when you suspect any generation problem:

| Gate | Command | Reading | Meaning of red |
|---|---|---|---|
| Agents | `uv run python build/generate_agents.py --validate` | pass is `VALIDATION PASSED`, exit 0 | `templates/agents/*.shared.md` and `src/` trees diverged |
| Mirrors and lib | `uv run python build/scripts/build_all.py --check` | pass is exit 0 | A `.claude/` canonical edit was not regenerated, or a generated tree was hand-edited |
| Install parity | `run_install_parity_ci.py` under `scripts/validation/` (run it through `instruments.py run install-parity`) | pass is exit 0 (ADR-035) | An install surface diverged between hosts |

- `build_all.py --check` exits 2 on staleness, on a path under `OWNED_PREFIXES` that cannot be read, redirects (symlink or junction), or holds a nested git repository, and on a generator writing under `.claude/` (REQ-003-010); it exits 3 when it cannot read git state (the `EXIT CODES` block in the `build/scripts/build_all.py` module docstring). Read the stderr line before reaching for the staleness remedy: regenerating and committing fixes only the staleness producer, not the exit-3 git cause and not the other three exit-2 ones. Its log legitimately says `Mode: Generate` mid-run; the snapshot/restore guard (#2440) makes the owned trees read-only, but not the whole run: `write_audit` creates or overwrites `build/audit/GENERATION-AUDIT.md` on every invocation, and that path is outside the snapshot, so restore never touches it. The file is gitignored (`/build/audit/`) and untracked: it exists only after a build run.
- Trap, the expensive one: drift output shows a DIFFERENCE, not a DIRECTION. On 2025-12-15 an agent "fixed" drift by editing the canonical source to match the stale generated tree (commit reverted). Before fixing any drift red, answer "which side is the source of truth?" via `.agents/governance/GENERATOR-FILES.md`, then see `ai-agents-generation-and-release` for the regeneration workflow.

### Guard telemetry and maturity tiers (retired)

RETIRED, not just as an instrument but entirely: issue #5154 deleted
`push_guard_base.py` and every push guard built on it, so nothing emits the
`EVENT={...}` stderr line any more, and in the same change it deleted the
now-producer-less classifier skill and its two build scripts (an
aggregator and a classifier) rather than leave them measuring nothing.
Tier semantics (Harmful, Proficient, Mature, Inert, Growing,
Budding, keyed on age/intercepts/fitness) are documented for historical
reference in `.project-toolkit/retrospective/` entries that cite this instrument; there
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

- File-set sensitivity (#1963): a `--cov-fail-under=100` pin is only valid with the exact test-file set it was calibrated with. CI's own comment records that a drifted set "alone now reports 63% and trips --cov-fail-under=100" (the comment above the REQ-009 collection step in `.github/workflows/pytest.yml`, near line 510).
- Module-name form (#2063): use `--cov=scripts.ai_review_common.verdict` style (dotted module), never a file path. The file-path form yields "Module never imported" and 0% coverage on pytest-cov 7.x / Python 3.14 (see the REQ-009 coverage steps in `.github/workflows/pytest.yml`, near lines 526-541, for live examples).

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

## Current Baselines

Run `python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/ai-agents-diagnostics-toolkit/scripts/baseline_snapshot.py" --repo .` for the live numbers. It does not run `build_all.py --check`, so the agent drift, mirror drift, and install parity readings need their own commands above.

Numbers move with every merge and with untracked files in the tree, so none are typed here: use `baseline_snapshot.py`. Golden principles reads red (exit 10) on main. The description budget passes its CI ceiling (`.github/workflows/skill-passive-compliance.yml`, `scripts/skill_description_budget.json`).

Guard telemetry and maturity tiers is not in this list: it was retired under ADR-084 (issue #5154). Re-measure before trusting any number here.
