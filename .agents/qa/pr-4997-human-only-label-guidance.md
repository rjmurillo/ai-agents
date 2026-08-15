---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-14-session-14706-a225da30e-fix-4782-human-only-label-guidance.json
qaCommit: c7e1ff3339e5111c92226a3b56d79ef9841d4c43
---

# QA Report: PR #4997, issue #4782, enforcement messages naming a human-only label

## Scope

Branch `fix/4782-push-gate-human-only-label`, base `a225da30e`
(origin/main), validation commit `c7e1ff3339e5111c92226a3b56d79ef9841d4c43`.

Under test: three enforcement messages that named a bypass label as the
reader's own next step, the two CONTRIBUTING.md lines with the same shape,
the GOTCHAS.md entry with the same shape, and the new guard tests that pin
all of them.

## Verdict

PASS.

## Acceptance criteria

| AC (issue #4782) | Evidence |
| --- | --- |
| Push-gate message no longer instructs the reader to apply `commit-limit-bypass` | `scripts/validation/git_hook_policy.py` message rewritten; pinned by `test_push_gate_over_the_needs_split_cap_defers_the_bypass_to_a_maintainer` |
| The message names the sanctioned action | Every rewritten message states the split (or the description repair) first |
| The message names the human-maintainer authority | All three cite CONTRIBUTING.md by section heading; pinned by `_assert_defers_to_a_maintainer` |
| The message forbids self-application | All three end with "do not apply it yourself"; pinned by the same helper |
| Audit the other bypass surfaces named in the issue | Recorded below under "Audit result" |
| Docs agents read carry the same constraint | `CONTRIBUTING.md` lines 857 and 910, `.agents/governance/GOTCHAS.md` line 251 |
| Regression coverage | `tests/validation/test_human_only_label_guidance.py`, 9 tests |

## Tests

```text
uv run pytest tests/validation/test_human_only_label_guidance.py \
  tests/ci/test_pr_validation_workflow.py \
  tests/workflows/test_pr_validation_needs_split.py \
  tests/test_pr_description.py tests/test_validation_pr_description.py \
  tests/validation/test_git_hook_policy_atomic_commit.py \
  tests/test_check_pr_bypass_label.py tests/validation/test_pr_commit_count.py -q
567 passed in 8.93s
```

The 9 new tests split into 6 positive assertions (both CONTRIBUTING.md
citations still resolve, scoped to the section each names; no CONTRIBUTING.md
line pairs an imperative with a human-only label without naming the
authority; the GOTCHAS.md entry names the same maintainer-only constraint;
each of the three enforcement messages defers to a maintainer) and 3
no-over-fire controls (push gate under the cap, CI blocker with the label
already present, description validator on a clean description) proving the
allowed paths carry no self-service instruction to apply the label. Two of
the three never name the label at all; the third (CI blocker with the label
already present) drops the "do not apply it yourself" lecture but still
prints a bypass-applied notice naming the label
(`scripts/ci/enforce_pr_validation.py:73`).

`tests/ci/test_pr_validation_workflow.py::TestBlockedMessageNamesTheLimitThatWasApplied::test_the_remediation_survives_every_shape`
asserted the old contract (`"split this PR"`, lowercase, from the removed
sentence). It is flipped in the same diff to the new contract plus the
prohibition, so no test asserts both shapes.

## Negative control

Four mutants, each restoring one pre-fix message verbatim, `__pycache__`
purged between mutation and rerun, occurrence count asserted before
patching and restoration asserted after:

| Mutated source | Killing test | Result |
| --- | --- | --- |
| `scripts/validation/git_hook_policy.py` | `test_push_gate_over_the_needs_split_cap_defers_the_bypass_to_a_maintainer` | DEAD (rc=1) |
| `scripts/ci/enforce_pr_validation.py` | `test_ci_blocker_defers_the_bypass_to_a_maintainer` | DEAD (rc=1) |
| `scripts/validation/pr_description.py` | `test_description_validator_defers_its_bypass_label_to_a_maintainer` | DEAD (rc=1) |
| `CONTRIBUTING.md` | `test_contributing_never_instructs_without_naming_the_authority` | DEAD (rc=1) |

Inverted control on the unmutated tree: PASS (rc=0). A guard that cannot
fail proves nothing, so the suite is only evidence because all four
mutants died and the unmutated tree passed.

## Lint

- `uv run ruff check` on all five changed Python files: All checks passed.
- `uv run ruff format --check`: reports `scripts/validation/git_hook_policy.py`
  and `tests/ci/test_pr_validation_workflow.py` as reformattable. Pre-existing,
  not introduced here: the same command against the `origin/main` blobs of both
  files reports the same two files. The repo's `python-check` pre-commit job
  passed on the staged set.
- `npx markdownlint-cli2 CONTRIBUTING.md .agents/governance/GOTCHAS.md`:
  "Linting: 1 file, Summary: 0 issues". `.agents/governance/GOTCHAS.md` was
  **NOT LINTED**: `.markdownlint-cli2.yaml` excludes `.agents/**`, so this PASS
  covers `CONTRIBUTING.md` only.

## Audit result for the other surfaces the issue named

Checked and deliberately unchanged, because they are not the same defect:

- `scripts/ci/show_drift_failure.py:41-48` (`[skip-drift-check]`) already
  lists "Ensure explicit code-owner approval on this PR" inside its bypass
  procedure.
- The lefthook `SKIP_*` variables either report after the fact ("YAML lint
  skipped (SKIP_YAMLLINT=1)") or explicitly deny ("SKIP_CLI_E2E=true cannot
  bypass a required CLI E2E gate").
- `scripts/detect_scope_explosion.py:427` prints `SKIP_SCOPE_CHECK=1 git push`,
  but no document declares that variable human-only, so it is a different
  authorization model, not an instruction to self-grant a reserved permission.
- `scripts/validation/check_pr_bypass_label.py` reports label presence without
  recommending it; `scripts/validation/pr_commit_count.py` defers enforcement
  without naming a remedy. Both are already correct.

## Risks

- The clause is duplicated across three modules instead of imported.
  `.github/workflows/pr-validation.yml:212` runs
  `python3 scripts/ci/enforce_pr_validation.py` with nothing installed, so a
  cross-tree import there could take a required check red on every PR. The
  guard test is the executable single source of truth that keeps the copies
  aligned.
- The messages cite CONTRIBUTING.md section headings, not line numbers. A
  heading rename breaks the guard test rather than leaving three silently
  dangling citations, which is the intended failure direction.
