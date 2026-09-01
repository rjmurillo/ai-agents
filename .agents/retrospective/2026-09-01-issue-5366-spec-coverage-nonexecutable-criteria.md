# Retrospective: Issue #5366 (spec coverage fails closed on criteria it cannot execute)

## Session Info

- **Date**: 2026-09-01
- **Agent**: Claude Code (fleet worker, isolated external worktree)
- **Task Type**: Bug fix, CI gate correctness
- **Outcome**: Success

## What shipped

Two commits on `claude/fix-5366-spec-coverage-nonexecutable`:

- `5fe383aa0` `fix(ci): classify unexecutable acceptance criteria for spec
  coverage`. New `scripts/ci/spec_nonexecutable_criteria.py` classifies
  acceptance-criteria bullets that assert the outcome of running a command,
  and `scripts/ci/spec_prepare_context.py` renders them as a
  `## Non-Executable Criteria Declaration` in the reviewer's additional
  context.
- `f1bc2356a` `fix(ci): tell the spec reviewer to mark command claims N/A`.
  Passes `PR_BODY` to the context step, adds the
  `## Non-Executable Criteria (fix #5366)` section to
  `.github/prompts/spec-check-completeness.md`, and adds one line of author
  guidance to the PR template's acceptance-criteria comment.

## Root cause

The `Validate Spec Coverage` job feeds a PR's own `## Acceptance criteria`
list to a reviewer that sees a diff and has no shell.
`scripts/ci/build_ai_review_context.py:296` injects the PR body verbatim as
`## PR Description`, so a criterion phrased as a command-execution claim
reaches a reviewer that structurally cannot satisfy it. The reviewer does the
only honest thing available and marks it `[~] PARTIALLY SATISFIED`. `PARTIAL`
is a failure token in `scripts/ai_review_common/verdict.py:216`:

    _COMPLETENESS_FAILURES = frozenset({"CRITICAL_FAIL", "FAIL", "PARTIAL", "NEEDS_REVIEW"})

so one such line fails the whole gate closed on every re-run, permanently,
regardless of the implementation. PR #5350 lost a run to this with 7 of 8
criteria SATISFIED.

The escape hatch that already existed, the Incremental Scope Declaration from
issue #2255, keys off the PR title and covers "this criterion belongs to
another phase". It has no shape for "this criterion describes a run the
reviewer cannot perform".

## Failure mode classification

**FM-10, Silent Defaults and Guard-Clause Suppression**
(`.agents/governance/FAILURE-MODES.md:315`). Not a new class.

FM-10's governing principle is "there is no neutral default for a missing
signal", and its listed shape is a verdict parser that turns absence of signal
into a verdict token. This is that shape with the polarity flipped. The
reviewer had three verdict tokens for a criterion (satisfied, partial, not
satisfied) and none of them means "not answerable from here". Absent a fourth
option it emitted the token that reads as an honest partial, and the
aggregator read that token as a failure. The missing signal became a blocking
signal with nothing at the seam recording that a signal was missing at all.

Issue #2006, already cited under FM-10's Evidence, is the same seam: security
agent output truncated, parser fell through to `NEEDS_REVIEW`, PR blocked
twice despite a substantive PASS. FM-10's Enforcement Pattern prescribes the
fix taken here: give the missing case its own token instead of laundering it
into an existing one. `N/A` is that token, already understood by the prompt
from the #2255 work, plus a deterministic path to reach it.

## Design choice: two halves, deliberately unequal

The issue offered three options. Two shipped, in a specific relationship:

- The prompt rule is the load-bearing half. It applies to any
  command-execution claim, whether or not the classifier found it.
- The deterministic classifier is the reliable half. It removes the
  classification from the model's judgment for the cases it can recognize.

That ordering let the classifier stay narrow. It fires only when a criterion
BOTH names a runnable command in an inline code span AND asserts an execution
result in intransitive position. "The helper passes the flag through to
`run_gh`" does not match, and neither does "`pre_pr.py` passes the changed-file
list to ruff".

The asymmetry is the point. Under-firing costs nothing, because the prompt rule
still covers the criterion. Over-firing would silently drop a real criterion
from the gate, which turns the check green while measuring less than it claims.
Option 2 as literally written in the issue, stripping bullets in
`build_ai_review_context.py`, was rejected for the same reason plus blast
radius: that builder feeds every AI review flow in the repo, not just spec
validation.

## Evidence

- `uv run --frozen python -m pytest tests/ci/test_spec_nonexecutable_criteria.py
  tests/ci/test_spec_prepare_context.py tests/ci/test_spec_extract_refs.py
  tests/ci/test_ci_scripts_are_wired.py tests/test_check_spec_failures.py
  tests/test_verdict.py tests/ci/test_validate_ai_review_budgets.py -q`:
  299 passed, 11 skipped.
- `uv run --frozen python scripts/validation/pre_pr.py`: `RESULT: All
  validations passed`.
- Negative control: replacing the body of `find_nonexecutable_criteria` with
  `return []` turned 25 of the new tests red, including both
  `test_includes_nonexecutable_criteria_block` and
  `test_emits_both_declarations_together`. Restoring it returned all 38
  detector tests and 14 context tests to green. The over-fire controls stayed
  green in both states, which is correct: they assert an empty result.
- `TestDoesNotOverFire` carries eight criteria a reviewer can check from the
  diff and asserts none of them is classified away.

## Remediation

| # | Action | Owner | Status |
|---|--------|-------|--------|
| 1 | Deterministic classifier for command-execution criteria, rendered as a `## Non-Executable Criteria Declaration` | PR #5451 | Shipped (`5fe383aa0`) |
| 2 | Prompt rule directing `N/A` instead of `PARTIALLY SATISFIED`, so the classifier is not load-bearing | PR #5451 | Shipped (`f1bc2356a`) |
| 3 | Author guidance in the PR template: command evidence belongs under Testing or Author Pre-flight | PR #5451 | Shipped (`f1bc2356a`) |
| 4 | Tie the command reference and the result verb to one clause, so a behavioral contract is not classified away | PR #5451 | Shipped (review round, see below) |
| 5 | Anchor the Acceptance Criteria heading match, so "Acceptance Criteria Verification" is not read as the criteria list | PR #5451 | Shipped (review round, see below) |
| 6 | Narrow the prompt exemption to historical run evidence, keeping command-shaped behavioral contracts in scope | PR #5451 | Shipped (review round, see below) |
| 7 | Reject a conditional criterion whole instead of truncating it, so a fragment cannot read as run evidence | PR #5451 | Shipped (review round 2) |
| 8 | Anchor the result tail to the end of the criterion, so a bullet that also carries a requirement stays in scope | PR #5451 | Shipped (review round 2) |
| 9 | Require the command claim to open the criterion, closing the mirror of row 8 where the requirement comes first | PR #5451 | Shipped (review round 3) |
| 10 | Keep an explicitly unchecked criterion in scope, since the template makes an unchecked box an admitted gap | PR #5451 | Shipped (review round 3) |
| 11 | Skip fenced code blocks, so a quoted sample section never joins the real gate | PR #5451 | Shipped (review round 3) |

No tracking issue is open against this work. Items 4 through 11 came from three
review rounds on PR #5451 (Devin and Copilot, independently, on the same
seams) and shipped in the same PR rather than as follow-ups.

Deliberately not fixed, with reasons:

- The classifier reads only inline code spans. A criterion that names a
  command in plain prose ("all tests pass") is not detected and falls to the
  prompt rule. That is the intended split, not a gap to close by widening the
  regex.
- Rejecting a conditional criterion whole also drops a real claim written with
  a leading adverbial ("after the rename, `pytest` passes"), and anchoring the
  tail drops one with a trailing qualifier ("`pytest` passes with the new
  flag"). Both are under-firing, which the prompt rule covers. Widening either
  back would re-admit an over-fire a review round closed.
- `PR_BODY` is empty on `workflow_dispatch`, which has no `pull_request`
  payload. The declaration is then absent and the prompt rule carries the
  case alone. Covered by
  `test_omits_nonexecutable_block_when_pr_body_is_absent`.
- Noticed on the path, not fixed here:
  `.serena/memories/pr-autofix/pr-5438-main-red-multi-session-race.md` is
  committed with CRLF line endings and shows as modified in a clean worktree
  because `.gitattributes` normalizes it to LF. Unrelated to this issue. No
  issue filed: the repair is one `git add --renormalize` on that path and does
  not need tracking to survive.

## +/Delta

**+**: The issue named the root cause precisely and cited the run IDs, so the
session spent its time on the fix rather than on reproduction. The existing
Incremental Scope Declaration gave the fix a shape to mirror, down to the
context-injection seam and the prompt's rule numbering.

**Delta**: The first draft checked "names a command" and "asserts a result"
as two independent scans over the same bullet, and the eight negative controls
in `TestDoesNotOverFire` all passed because every one of them fails both
checks, not just one. Two reviewers found the same gap within four minutes:
"the wrapper returns zero when `pytest` passes" satisfies both scans and is a
behavioral contract the gate must keep. A negative control that only exercises
the conjunction of two predicates cannot tell you the conjunction is the wrong
shape. The six cases added in the review round each satisfy one predicate and
must still stay in scope, which is the control the first draft was missing.

**Delta**: Round 3 turned up a control that passed for the wrong reason. Three
of the four fenced-sample fixtures written first were green against the
unfixed code, not because fences were handled but because a closing fence on
the line after the bullet folds into that bullet and the result tail then
refuses it: two unrelated rules cancelling out. Running the fixtures against
the unfixed code before writing the fix is what surfaced it; the shipped
controls are the shapes that actually leaked (blank line before the closing
fence, unclosed fence, tilde fence). A control that has never been observed
failing is a claim about coverage, not evidence of it.

**Delta**: The first repair narrowed by salvaging rather than rejecting, and
each salvage leaked. Truncating a conditional at its subordinator left
"`wrapper.py` returns zero", a fragment whose command span is the script under
test rather than the command the sentence conditions on, so the criterion was
still classified away. `Pattern.match` succeeding on a prefix let "`pytest`
passes locally and the parser rejects an empty ref" match on "locally" alone,
classifying a bullet that carried a real requirement. Both fixes replace a
salvage with a rejection. When the safe failure direction is known, reject on
partial recognition instead of working with what survived the trim.

**Delta**: The first draft of `_RESULT_TAIL` used `^` with
`Pattern.match(text, pos)`. In a non-multiline pattern `^` anchors to the start
of the string, not to the position handed to `match()`, so the tail check never
matched and every positive test failed at once. A uniform failure across all
positives is a signal about the harness, not about the cases; reading it that
way found the bug in one probe.
