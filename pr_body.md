# fix(eval): correct measurement and provider defects across the eval subsystem

This PR fixes measurement and provider defects across the eval subsystem.

## Changes

### Judge scoring (fixes #3915, #3933, #3958)

`_reduce_score_samples` now computes the mean over graded (non-failed) samples
only. Failed judge calls no longer drag down the score toward zero, which
previously inverted mechanism rankings.

`_mechanism_summary` now returns both `judge_failure_cells` (count of failed
cells) and `judge_failure_samples` (count of samples where all cells failed),
making the distinction clear in output artifacts.

A new `FAIL_OVERACTIVATION` verdict fires when the negative scenario mean
exceeds the allowed activation threshold. Previously negative scenarios could
not fail a rule verdict.

### Run provenance (#3956)

`_build_run_provenance()` adds a `run` object to output artifacts, recording
git SHA, timestamp, and branch. This makes result artifacts traceable to the
commit that produced them.

### API key selection (#3924)

`load_api_key_for_selected_provider()` in `_anthropic_api.py` returns the
Anthropic API key when `EVAL_PROVIDER` selects an Anthropic-backed provider,
and returns `""` otherwise. All 8 eval entry points now use this function,
so they no longer require `ANTHROPIC_API_KEY` when running against a keyless
provider.

### Rule scenarios (#3935)

Added `tests/evals/rule-scenarios/code-quality.json` and
`tests/evals/rule-scenarios/pragmatic-programmer.json` with 4 scenarios each
(2 positive, 2 negative). These cover the two largest always-on rule files
that previously had no eval coverage.

### Rule-audit pre-registration (#3957)

Added `.claude/skills/context-optimizer/references/rule-audit-procedure.md`
documenting that the sign-counting decision rule must be registered before
running any scored eval. This prevents retroactive rule selection after
seeing the results.

### Size-ceiling exemptions (#3592)

Added `# taste-lint: ignore file-size` directives to 3 Python files that
exceed the size ceiling due to accumulated, tightly coupled logic where a
split would increase rather than decrease complexity.

### Token budget measurement (#3906)

Added a "Token Budget Measurement" section to `scripts/eval/README.md`
documenting that `instruction_budget.py` is the correct tool for offline
token measurement. Clarified why live Copilot CLI token counts are unsuitable
as a measurement tool.

### Model panel documentation (#3905)

Updated `_model_panel_core.py` docstring to be explicit that the default panel
contains placeholder model IDs pending verified data. Added a TODO comment in
`_eval_common.py` marking the rows that need real pricing figures.

### Judge parse failure evidence (#3975)

Judge parse failures previously stored only a 200-character prefix of the raw
response in the `reasoning` field. A long response would be silently truncated,
destroying the evidence and potentially fabricating a cause from an incomplete
fragment.

The fix removes the truncation. On a JSON parse failure or a non-object JSON
result, the full raw response is stored in a new `raw_judge_response` field and
the `reasoning` field contains a neutral, non-fabricated message. Successful
parses are unchanged; no `raw_judge_response` field is written on the happy
path.

## Issues closed as stale

Issue #3934 (`eval: copilot-cli provider measures user-prompt priming`) was
closed because the `_CopilotCLIProvider` class it describes does not exist in
`scripts/eval/_providers.py` on main. The issue referenced code from an
unmerged branch (PR #3513). No fix needed.

## Deferred

Issue #3552 (`eval: the test group split produces has no read path in the CLI`)
requires a new `report` subcommand with a distinct design. This is an ADR-087
open requirement, not a quick fix.

## Fixes

Fixes #3915
Fixes #3933
Fixes #3956
Fixes #3958
Fixes #3924
Fixes #3935
Fixes #3957
Fixes #3592
Fixes #3906
Fixes #3975
