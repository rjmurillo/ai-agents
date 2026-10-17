# skill-bootstrap: before and after the six capability changes

Run `20261017T164000Z-2e1e279c`, 2026-10-17. Before: `acff1d0a1` (skill-bootstrap as merged in #6608).
After: `2f94efa39` for T1 to T3 and the behavioral run, `a2719e206` for T4 (adds the
skill-relative `claims` fix). Raw records are under `../../runs/20261017T164000Z-2e1e279c/`.

## What changed

1. Phase 3 sorts every verified item as `scaffold` (prose), `instrument` (script), or `both`; `bootstrap_forms.py check` refuses a computable item without a script.
2. The authoring brief requires every computable claim to ship a script with tests.
3. Phase 5 builds a frozen capability eval and scores each skill with and without it (`bootstrap_eval.py freeze`, `score`).
4. Each authored skill ships `reverify.json`; `bootstrap_drift.py check` names the skills that need `--update`.
5. `knowledge` mode gates a lens by verified content plus a failing baseline case, not by friction.
6. Discovery starts from `bootstrap_mine.py candidates` (reverts, churn, TODO hotspots, review rounds); `claims` checks authored text against a named ref.

## Layer 1: behavioral (repository harness)

`scripts/eval/eval-rule-activation.py` on `tests/evals/skill-scenarios/skill-bootstrap.json`
(17 scenarios: S1 to S11 existing, S12 to S17 added before any implementation, one per change).
Provider `claude-cli` with `EVAL_RUNTIME_REAL_HOME=1`, responder and judge `claude-sonnet-5`,
3 judge samples per cell, median. Scores are 1 to 5.

| Group | Mechanism | Before | After |
|---|---|---|---|
| S12 to S17 (new behavior) | full skill | 2.17 | **5.00** |
| S12 to S17 | description only | 2.06 | 3.28 |
| S12 to S17 | no skill (control) | 2.11 | 2.06 |
| S1 to S11 (regression check, positive cases) | full skill | 4.13 | 4.10 |
| S1 to S11 | no skill (control) | 3.07 | 3.20 |
| All positive | full skill | 3.40 | 4.44 |
| Negative case S8 | full skill | 5.00 | 5.00 |

Per scenario, full skill, before to after: S12 1.67 to 5.00, S13 5.00 to 5.00, S14 1.00 to 5.00,
S15 2.00 to 5.00, S16 1.00 to 5.00, S17 2.33 to 5.00. S13 sits at ceiling in every cell, so it
does not discriminate. The runner's verdict is `FAIL_THRESHOLD` in both runs; it gates on the
description mechanism against baseline, which was below threshold before this change too.

Reading: the new text transfers. With the skill loaded, a model now sorts items by tool form,
builds the capability eval instead of reporting UNMEASURED, uses the drift loop, picks knowledge
mode for a handoff, and mines candidates with the script. Existing behavior did not regress.

## Layer 2: capability on this repository

`scripts/eval/eval_skill_bootstrap_capability.py`, tasks in `../../fixtures/tasks.json`. Each run is
`claude-haiku-5-5` through `claude -p` in a checkout that carries one skill version, with tools
on and file edits disallowed. Answers are graded against gold derived independently of the new
scripts. 3 runs per task per condition.

| Task | F1 before | F1 after | Precision before | Precision after | Turns before | Turns after | Cost before ($) | Cost after ($) |
|---|---|---|---|---|---|---|---|---|
| T1 stale refs in 15 ai-agents-* skills | 0.867 | 0.872 | 0.778 | 0.790 | 18.3 | 17.0 | 0.128 | 0.183 |
| T2 reverts in history | 1.000 | 1.000 | 1.000 | 1.000 | 4.0 | 5.7 | 0.022 | 0.055 |
| T3 churn top 3 | 1.000 | 1.000 | 1.000 | 1.000 | 4.3 | 5.3 | 0.028 | 0.069 |
| T4 out-of-range line refs in all 121 skills | 1.000 | 1.000 | 1.000 | 1.000 | 6.7 | 11.3 | 0.026 | 0.048 |

Reading: no accuracy gain, and cost rose 1.4x to 2.5x. Haiku with a shell writes its own
throwaway script for a crisply defined computation, so a shipped instrument does not beat it on
these tasks; the agent pays to read the longer skill. T1's remaining errors are judgment errors
(a manifest path the text marks retired), which no script removes. This layer does not show the
instruments raising capability. It does not rule out value this design did not measure:
reproducible answers across agents and sessions, and cost on repositories where an ad hoc
script is harder to write. Those stay candidates.

## Corrections made during the run

- T2 gold: the first derivation read 3354 commits; a later fetch moved the shallow boundary to
  3559 and exposed three squash merges whose bodies carry `This reverts commit` lines. The
  before-run agents found them. Gold was corrected to all 9 and both conditions were re-graded.
- T1 ignore list: `.claude-plugin/plugin.json` in four skills is a generic name for the
  per-plugin manifests, so it is ambiguous; both conditions were re-graded without it.
- T4 was added after round one and frozen before either condition ran it.
- The library-wide T4 investigation found a defect in `claims`: a skill's own `scripts/x.py`
  resolved only from the repository root. Fixed in `e1d09ceec`; current findings across all
  121 skills fell from 141 to 90.

## Findings outside the task

<!-- citation-freshness: ignore -- these AGENTS.md line numbers are the stale citations this finding reports, not citations this report relies on -->
- `.claude/skills/ai-agents-research-methodology/SKILL.md:275-276` cites `AGENTS.md:40` and `AGENTS.md:38`; `AGENTS.md` has 24 lines.
- `ai-agents-architecture-contract`, `ai-agents-portability-campaign`, and `ai-agents-research-frontier` cite `tests/build_scripts/test_copilot_dispatcher_artifact.py`, deleted by `f79e70c01` (ADR-097).
- `.claude/skills/ai-agents-config-catalog/SKILL.md:122` lists `.claude/.claude-plugin/plugin.json` as a live manifest; it is retired.
