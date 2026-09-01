# Retrospective: Issue #5104 (CodeQL check-blocking-issues cancellation guard)

## Session Info

- **Date**: 2026-09-01
- **Agent**: Claude Code (fleet worker, isolated external worktree)
- **Task Type**: Bug fix (CI reliability), single issue
- **Outcome**: Success. The PR shipped the cancellation guard, the classifier widening, and the retrospective record for Issue #5104.

## Failure Mode Classification

**Primary**: No existing `FAILURE-MODES.md` class cleanly matches.
Issue #5145 tracks the proposed class `State Conflation in a Boolean Guard`.

PR #5103 did not miss this job. Its audit table flagged
`codeql-analysis.yml::check-blocking-issues` as outside the result-reading
shape and left it as a follow-up. Issue #5104 cites that audit, not a live
reproduction. The defect here is the job's `always()` guard on a PR head: it
collapses cancellation and failure into the same visible red path on a
superseded head. That shape is not FM-9, and it is not FM-10 because nothing
is hidden.

The fix in this PR does not just patch the instance; it widens the classifier
itself (`depends_on_upstream_output`) so the artifact-consuming shape is part
of the checked contract going forward.

## What shipped

`.github/workflows/codeql-analysis.yml::check-blocking-issues` ran under
`always()`. The workflow sets `cancel-in-progress`, so a push that supersedes
a run cancels the `analyze` matrix legs before they reach their
`Upload SARIF artifact` step. The `always()` gate then ran
`check-blocking-issues` anyway, its `actions/download-artifact` step errored
on artifacts that were never uploaded, and GitHub recorded a red check run
against a head nobody was waiting on.

Implementation on `claude/fix-5104-codeql-cancelled-guard`:

- `fix(ci): guard codeql check-blocking-issues against cancelled runs`.
  Swapped `always()` for `!cancelled()` (the substitution PR #5103 applied to
  the five result-reading aggregators), and widened the classifier that
  powers the repository-wide sweep in
  `tests/workflows/test_aggregator_cancellation_guard.py` so the sweep
  covers this job's shape.

## The interesting part: why the #5097 sweep left this open

PR #5103 audited every `needs` + `always()` job and fixed five. Its audit
table flagged this job but deliberately left it open because it never reads a
dependency result. Issue #5104 reports that follow-up. The sweep's
classifier, `_consumes_dependency_results`, defined an aggregator as a job
whose payload matches
`needs\.[A-Za-z0-9_-]+\.result|toJSON\(\s*needs\s*\)`.

`check-blocking-issues` matches neither. It never reads a dependency result.
It depends on upstream work through downloaded artifacts instead, and its
only `needs.` reference is `needs.check-paths.outputs.should-run-analysis`,
which lives in `if:` and is deliberately excluded from the payload scan.

So there are two distinct ways a job can depend on upstream work, and both go
red identically under `always()`:

1. Read `needs.<job>.result`, score the `cancelled` value, exit non-zero.
   That is #5097.
2. Download an artifact the upstream job never uploaded because cancellation
   reached it first, and let `actions/download-artifact` error. That is
   #5104.

The fix that actually closes the class, rather than this one instance, lives
in the repository-wide sweep module itself:
`depends_on_upstream_output = _consumes_dependency_results or
_consumes_dependency_artifacts`. The sweep now sees both shapes.

## What went right

**Measured the blast radius before widening the classifier.** Broadening a
repository-wide sweep is the kind of change that quietly turns one issue into
a twelve-job refactor. Before editing anything I ran a throwaway probe that
applied the proposed classifier across `.github/workflows/*.yml` and printed
every job it would newly examine. Result: exactly two, this job and
`pytest.yml::coverage`, and the latter was already guarded with
`!cancelled()`. That single measurement turned "is this scope creep?" from a
judgment call into a number, and justified raising
`MINIMUM_AGGREGATORS_EXAMINED` from 5 to 7 with evidence rather than by
adjusting it until tests passed.

**Two negative controls, not one.** The obvious control is reverting the
workflow. I also ran the less obvious one: revert the classifier widening
while keeping the workflow fixed. Both were needed and both found something.

- Workflow reverted, tests kept: 3 failures, and the sweep named
  `codeql-analysis.yml::check-blocking-issues` by id.
- Classifier reverted, workflow kept: 3 failures, on the examined floor and
  the two new sweep cases.

The second control is what proves the sweep widening is load-bearing rather
than decorative. Without it, a reviewer could not distinguish "the sweep now
covers artifact consumers" from "a new fixture entry was added and the sweep
is unchanged." Adding the job to `FIXED_AGGREGATORS` alone would have passed
the first control and taught nobody anything.

**Named the inverse before writing the fix.** Widening a detector has a
standing obligation: prove it does not over-fire. The mirror case here is
`actions/upload-artifact`, the step the analyze legs themselves run. A
classifier matching `artifact` loosely would tag every producer job as an
aggregator and demand cancellation guards from jobs that depend on nothing.
`test_uploading_an_artifact_does_not_count` pins that, and matching the
literal action reference rather than a step name is what makes it hold.

## What to watch

**The premise test had to be generalized, and that is a real trade.**
`test_aggregator_still_reads_dependency_results` existed to fail loudly if a
job stopped being the thing the module describes. Renaming it to
`test_aggregator_still_depends_on_upstream_output` and accepting either shape
weakens it slightly: a job that swapped a result read for an artifact
download would now pass silently. That seemed right, because both shapes need
the same guard and the guard is what the module protects, but it is a
loosening and worth knowing about.

**`MINIMUM_AGGREGATORS_EXAMINED` is now a number two changes have moved.**
The comment above it already carries the #5142 warning about raising it to
paper over a regression. I extended that comment with how 7 was measured and
which job the artifact classifier added. If a future change makes this number
move again, the honest move is still to re-measure and explain, not to adjust
until green.

**Two stale counts fixed on the way past.** The module docstring said
`MINIMUM_AGGREGATORS_EXAMINED` "reflects the five aggregators this module now
covers" and a comment read "The five jobs this change converted." Both became
wrong once this PR added a sixth guarded aggregator and a seventh examined
job (`pytest.yml::coverage`, already guarded). Fixed in the same commit rather
than left as a broken window, since I was editing the lines directly above
them.

## Process notes

- Verified no competing PR and no `PR-AUTOFIX-LEASE` marker on the issue
  before starting, per fleet protocol. Both clean.
- Worked in an external worktree at `/root/src/scratch/worktrees/fix-5104`
  per `.claude/rules/universal.md` ("Git worktrees MUST be external").
- `uv run --frozen python -m pytest tests/workflows/ -q`: 421 passed.
- `uv run --frozen python scripts/validation/pre_pr.py`:
  `RESULT: All validations passed`.
- No hook bypass used. The retrospective gate blocked the first push, which
  is what produced this file.

## Remediation

- [Complete] Issue #5104: workflow guard. Changed
  `.github/workflows/codeql-analysis.yml::check-blocking-issues` from
  `always()` to `!cancelled()` so a superseded run stops before the missing
  SARIF download path can fail red.
- [Complete] Issue #5104: classifier widening. Updated
  `tests/workflows/test_aggregator_cancellation_guard.py::depends_on_upstream_output`
  and `_consumes_dependency_artifacts` in the repository-wide sweep module so
  the sweep classifies both result-reading aggregators and
  artifact-consuming aggregators.

## Future observation

The sweep still classifies by pattern-matching workflow YAML, so any third way
a job can depend on upstream work, such as `gh run download` in a `run:` block
or a cache restore keyed on an upstream artifact, would be invisible to it the
same way the artifact shape was. That is not a defect to fix speculatively, but
it is the shape of the next miss if there is one.
