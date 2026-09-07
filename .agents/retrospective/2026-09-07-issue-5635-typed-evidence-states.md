# Retrospective: giving validators five states instead of two

**Date**: 2026-09-07
**Scope**: Issue #5635, branch `claude/autoplan-goal-zlu1ve`, 9 commits
**Failure mode classification**: #10, Silent defaults and guard-clause
suppression (`.agents/governance/FAILURE-MODES.md:26`). The defect being
removed, not one introduced. Secondary touch on #4, False completion markers:
one commit message quoted a ratchet count measured before the final edit to the
file it was counting.

## What happened

Several validators returned `bool`, so every outcome that was not "clean" or
"dirty" had to borrow one of those two words, and in this tree it always
borrowed `True`. `validate_session_end` returned `True` when the base ref would
not resolve and again when `git diff` exited non-zero. `validate_workflow_yaml`
and `validate_yaml_style` returned `True` when their linter was not installed.
`validate_mypy_changed_files` carried the same base-ref-and-diff pair. The
runner recorded all of them under `passed`.

The change adds `scripts/validation/evidence.py`: five states (PASS, FAIL, SKIP,
BLOCKED, UNKNOWN), a required machine-readable reason code on every non-PASS,
and a PASS that cannot be constructed without naming the revision and scope it
ran against. `pre_pr.py` records the typed outcome, aggregates worst-wins,
emits `--summary-json`, and exits on the worst blocking state. Four validators
migrated; the rest still return `bool` and are tagged
`legacy.boolean_contract` so the remaining work is countable.

## Impact

| Area | Severity | Effect |
|---|---|---|
| Gate honesty | High | Six not-checked conditions across four validators reported PASS |
| Diagnosability | Medium | A degraded run and a clean run printed the same line |
| Auditability | Medium | The SKIP carve-out lived in prose; it is now a reviewable `PolicyException` |

Measured on this branch: of 64 gates in the pre-PR sequence, 60 still carry the
unmigrated boolean contract. The scale of the remaining work was invisible
before the summary could count it.

## Root cause, five whys

1. Why did a base-ref failure report PASS? Because the function returned `bool`
   and `False` was reserved for a real violation.
2. Why was `True` the fallback rather than `False`? Because failing the push on
   a missing base ref would have been worse than passing, and there was no
   third option.
3. Why was there no third option? Because the runner's contract was
   `Callable[[], bool]`, so a validator could not express one.
4. Why did the runner's contract stay boolean? Because `MissingScriptSkip`
   already covered the one non-binary case anyone had needed, by raising rather
   than returning.
5. Why did that not generalize? Because an exception is a control-flow signal,
   not a value: it carries no scope, no revision, no counts, and cannot say
   *which* precondition was absent.

Root cause: **the runner's return type was the ceiling on what a validator
could say.** Every fail-open below it was a workaround for that ceiling rather
than a mistake in the validator.

## What went well

- **The full-corpus run found a real regression the unit tests could not.**
  `ci-scripts.md` MUST 13 requires quoting the gate's own command against the
  whole corpus before merge. The first run reported FAIL 1 / BLOCKED 2: the
  mypy gate caught a `**{field_name: -1}` kwargs splat in a new test and a
  pre-existing `no-any-return` whose line my diff had made "changed". Both were
  invisible to the 125 new unit tests, which all passed.
- **Negative controls were run, not assumed.** The subprocess-failure
  classifier was mutated twice: keying on the exit code alone failed 2 of its 8
  tests, keying on the stderr text alone failed 1, and the restored version
  passed all 8. Per `.claude/rules/testing.md` SHOULD 17, a probe whose result
  is not paired with a discriminating edit measures nothing.
- **The prior art was reused rather than reinvented.** `_harness_capability.py`
  (#5630) had already proved the shape: typed status, separate evidence kind,
  restrictive default, worst-wins precedence tuple. `verdict.py` had already
  established that an empty child set aggregates to UNKNOWN. Both are cited in
  the module docstring so the next reader does not re-derive them.

## What to improve

- **A dated ratchet count in a commit message is a measurement, not a fact.**
  One commit body claimed `taste count ratchet back to 564` after moving a
  helper out of `checks_common.py`. The claim was true when measured and false
  by the time the commit landed, because the explanatory comment added for the
  re-export pushed the file from 492 to 502 lines and back over the ceiling.
  Re-measure after the last edit to the file the number describes, not after
  the edit that motivated the number. Caught and corrected by amend before the
  push; the underlying rule is `ci-scripts.md` MUST 14's "re-measure" applied
  to one's own diff rather than to `main`.

- **Splitting a type contract across modules is not free in this directory.**
  `scripts/validation/` is imported both flat (`pre_pr.py` inserts the
  directory on `sys.path`) and as a package (tests use
  `scripts.validation.X`). A first attempt split `evidence.py` in two to clear
  the 500-line taste ceiling. That would have given the two import paths two
  distinct `EvidenceState` enum classes, and every `is` comparison across the
  seam would have returned `False` silently. Verified empirically: importing
  the same file both ways yields `pkg is flat` -> `False`. The module stayed
  one file with a justified `taste-lint: ignore file-size`, and every consumer
  imports it by its package path so there is exactly one identity. This is
  issue #3073's dual-module-identity trap arriving at a new site.

- **Migrating a producer means flipping its tests in the same diff, and the
  count is larger than it looks.** Four validators changed return type and 30
  test assertions across 8 files broke. Four of those tests were *named* for
  the defect (`test_returns_true_when_actionlint_missing`,
  `test_passes_when_no_base_ref`, `test_no_session_log_returns_true`,
  `test_skips_when_actionlint_absent`), so renaming was part of the fix, not
  cosmetics: a test named for the wrong outcome teaches the next reader the
  wrong contract. Budget for the flip when scoping a producer-contract change.

## Reusable rules

1. When a caller must distinguish more than two outcomes, widen the return
   type before adding a workaround. A fail-open guard clause is usually a
   symptom that the type is too narrow.
2. Before splitting a module that defines an enum or a dataclass used in `is`
   comparisons, check how its directory is imported. Two import paths mean two
   identities.
3. Run the gate against the whole corpus before claiming it is ready. Unit
   tests prove the checker's logic; only the corpus run proves the tree
   satisfies it.
4. Re-measure a count after the last edit to the file it describes.

## References

- Issue #5635. The typed evidence-state contract.
- Issue #5630. `CapabilityStatus`/`EvidenceKind`, the prior art this borrowed.
- Issue #3073. The dual-module-identity trap in `scripts/validation/`.
- `.claude/rules/ci-scripts.md` MUST 12, MUST 13, MUST 14.
- `.agents/governance/TESTING-RIGOR.md`, "Contract Changes: Flip the Stale Tests".
