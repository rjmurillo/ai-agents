---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-21-session-99927-9e1ebd2b8-adr-099-session-qa-binding.json
qaCommit: 9d8a6c28755fbd673a2fce59d4727f0fdbf072c2
---

# ADR-099 Session QA

## Scope

Code change: `.claude/lib/qa_report.py` (`QaBinding` gains `inconsistency`,
`session_qa_binding()` replaces its field-equality raise with the diagnostic),
mirrored byte-identical to `src/copilot-cli/lib/qa_report.py`, and
`scripts/validate_session_json.py` (`validate_qa_report_evidence()` surfaces
the diagnostic into `result.warnings`). Test change:
`tests/test_validate_session_json.py` (`test_rejects_qa_commit_disagreement`
replaced, five new unit cases, two wiring tests: the disagreement-warns
wiring test and the fallback-head-path test added per Implementation Note 8,
see below). Unrelated red-CI fixes
carried on the same branch: `tests/ci/test_validate_vendor_provenance.py`
(stale setup-uv SHA pin) and `.github/workflows/pytest.yml` (pip pin moved
past PYSEC-2026-3721). Everything else on this branch is ADR-099 and its
debate log, both documentation.

## Test Results

| Command | Result |
|---|---|
| `uv run pytest tests/test_validate_session_json.py -q` | 380 passed |
| `uv run pytest tests/test_validate_session_json.py -k "qa_report or qa or session_json or session_log" -q` | 565 passed |
| `uv run ruff check .claude/lib/qa_report.py scripts/validate_session_json.py tests/test_validate_session_json.py` | clean |
| `diff -q .claude/lib/qa_report.py src/copilot-cli/lib/qa_report.py` | identical |

## Discrimination Probe

Per `.claude/rules/testing.md` SHOULD 10: restored the deleted equality raise
as a mutant over `.claude/lib/qa_report.py`, cleared `__pycache__`, and
re-ran the full `tests/test_validate_session_json.py` suite. The mutant
failed exactly the three tests that assert the new precedence-and-diagnostic
behavior and left the three no-diagnostic control tests green, confirming
the suite actually distinguishes old from new behavior rather than passing
regardless.

## Corpus Blast-Radius Verification

Independently reproduced (not re-derived from the ADR's own numbers) against
`git ls-tree -r HEAD .agents/sessions/`: 1459 logs examined, 1418 with no
full-SHA `comparison.head`, 6 with a full `comparison.head` and a non-full
`endingCommit`, 35 with both fields full SHAs (34 agreeing, 1 disagreeing).
Sums to 1459. Re-running `session_qa_binding` over the corpus under the
implemented behavior: exactly one log's behavior changes, matching the
ADR's pre-implementation prediction.

Separately reproduced the debate's lockstep-history measurement against
`git log --all -- .agents/sessions/`: 50 edits to `comparison.head` across
38 single-parent commits, 44 with `endingCommit` present, 42 agreeing
(SHA-prefix-normalized), split 34 creations (fields born equal, nothing
moved) and 8 modifications (7 genuine hand-syncs, 1 no-op), plus 2 genuine
disagreements, both in commit `f7fc4ef88a5400be1c2102b40c9272c2629f0762`.
All figures match what is now committed in ADR-099 and its debate log.

## Review Process

`.claude/rules/ci-scripts.md` MUST-NOT-2 required an ADR before this code
landed; `.agents/architecture/ADR-099-session-qa-binding-field-precedence.md`
and its debate log (`.agents/critique/ADR-099-debate-log.md`) carry the
full record. The debate ran across three rounds: a disclosed single-reviewer
pass, a genuine six-agent debate (five Accept/Disagree-and-Commit, one
Block on the Context section's central claim), a Phase 2 conflict
resolution that overruled the Block against the Decision and upheld it
against the Context, and a scoped Phase 4 convergence check that caught
and corrected a second overstatement in the rewrite itself. No agent
Blocks the ADR as it now stands.

## Pre-Push Gate Evidence

`uv run python scripts/validation/pre_pr.py` reported `RESULT: All
validations passed` on this commit. The full `lefthook` pre-push suite,
including `python-tests` and `pre-pr-validation`, ran green on this commit
before the follow-up commits that only touch `.agents/sessions/` and
`.agents/qa/` (evidence-only paths per `QA_EVIDENCE_PREFIXES`).

## Post-Merge Rebind

`qaCommit` moved from `5484cc8a2` to `c6d7f388f` (a merge of `origin/main`,
which brought in PR #5219's ADR-096 frontmatter flip and an independent
setup-uv SHA-pin fix in `tests/ci/test_validate_vendor_provenance.py` that
conflicted with this branch's own generic-pattern version of the same fix).
Per `post_qa_code_changes()`'s documented merge-diff behavior (ADR-096
Negative consequence 1), a catch-up merge always reports as a code change
regardless of whether this branch's own diff changed, since `git log -m`
diffs against both parents. The merge conflict was resolved by combining
both fixes (parse the YAML structure per `testing.md` MUST 9, assert a
SHA-pattern rather than one exact SHA to avoid re-introducing the staleness
trap PR #5215 caused). `uv run pytest tests/test_validate_session_json.py -q`
re-run clean at 379 passed on the merge commit.

A second catch-up merge, `06fa514b5`, was required before the push
succeeded: `origin/main` advanced again while the first push was in flight,
landing PR #5225, which applied the exact same pip 26.1.2 to 26.2 bump this
branch had already carried in `.github/workflows/pytest.yml` (for the same
CVE, PYSEC-2026-3721) under a differently worded comment. `merge-tree-ratchet`
(a pre-push job that runs `git merge-tree` against `origin/main` and rejects
a push whose merged result would fail a registered ratchet) caught the
resulting conflict before it ever reached CI. Resolved by keeping
`origin/main`'s comment, which cites issue #5222 and is the version already
merged to main; the pin value itself (`26.2`) was identical on both sides, so
no code changed. `uv run pytest tests/test_validate_session_json.py -q`
re-run clean at 379 passed again on `06fa514b5`, and
`merge_tree_ratchet_check.py --base-ref origin/main` reported OK.

## Fallback-Head-Path Test (Implementation Note 8)

`ai-spec-validation`'s Implementation Completeness pass correctly flagged one
gap: ADR-099 Implementation Note 8 asked for a test pinning the
fallback-head-path exposure named under "The laxer direction is bounded, not
impossible", and no such test existed. Added
`test_fallback_head_masks_a_real_change_between_the_two_fields`: with
`validation_head=None`, `comparison.head` older than `endingCommit`, and
`report.commit` a genuine ancestor of `comparison.head`, the test asserts
both that the report still passes and that the two `git` commands
`post_qa_code_changes()` issues never name `endingCommit`, pinning the gap
described in the ADR rather than leaving it asserted only in prose.
`uv run pytest tests/test_validate_session_json.py -q` re-run clean at 380
passed (the new test plus all 379 prior). `qaCommit` moved to `21a23ec39`,
the commit carrying this test, since it is a real (non-evidence) change
that would otherwise correctly flag this report stale.

## Post-Review Rebind and a Cursor Bugbot Fix

After the PR was marked ready for review, Cursor Bugbot flagged a Medium
finding: this session log's `constraintsRead.Evidence` field attributed to
`session-logs.md` MUST 2 and MUST 3 the claim that `endingCommit` moves
independently of `comparison.head`, but those two MUST items only describe
`endingCommit`'s own update schedule (a follow-up commit, then re-point
after any rebase) and never mention `comparison.head` at all. Verified
against the rule file directly and confirmed the finding; fixed the
wording to describe only what the rule text actually says.

Landing that fix required merging `origin/main` again, which had advanced
by two commits (ADR-100 and ADR-101, both unrelated to this PR). Both new
files live outside `QA_EVIDENCE_PREFIXES`, so `qaCommit` moved again to
`3386b3cc5`, the commit carrying the Bugbot fix on top of the merge.
`merge_tree_ratchet_check.py --base-ref origin/main` reported OK and
`uv run pytest tests/test_validate_session_json.py -q` re-ran clean at 380
passed on this commit.

## Post-Review Rebind: Copilot Findings and a Cursor Bugbot Autofix Merge

Between the previous rebind and this one, two things landed. First, a branch
divergence: Cursor Bugbot's Autofix feature independently pushed its own fix
for the same Medium finding directly to the branch, applying different
wording to the same `constraintsRead.Evidence` field this session had just
fixed. Resolved with `git merge origin/claude/autoplan-ship-wi09a5 --no-edit`
(commit `c348f17a5`), keeping this session's more detailed wording on the
one conflicting line.

Second, GitHub Copilot's automated review of the PR returned eight
comments. One was a confirmed real bug: `QaBinding.inconsistency` was a
plain dataclass field, so the generated `__eq__`/`__hash__` compared and
hashed it along with `session_log` and `commit`, contradicting the class's
own docstring claim that it is "not part of that identity." Fixed with
`field(default=None, compare=False)`; a new test,
`test_inconsistency_is_excluded_from_binding_identity`, pins it (confirmed
to fail with the fix reverted, restored byte-identical afterward). Three
more were confirmed stale-prose survivors of the Phase 4 correction already
recorded above (the 34/8/7 split): the shipped code comment in
`session_qa_binding()`, the mirroring comment in
`scripts/validate_session_json.py`, and the comment on
`test_binds_to_comparison_head_when_commit_fields_disagree`, all still
describing the debate's refuted "42-of-44 lockstep" framing. Two more were
the same drift inside the ADR itself (Measured Incidence, Why Change Now,
Alternatives Considered). One finding was design-level pushback on the
already-debated, already-accepted fallback-head-path trade-off; answered
with a reply rather than a design reversal, per this repo's PR-stewardship
rules for a settled multi-agent-reviewed decision.

`src/copilot-cli/lib/qa_report.py` regenerated byte-identical via
`uv run python build/scripts/build_all.py`.
`uv run --frozen pytest tests/test_validate_session_json.py -q` re-ran clean
at 381 passed (380 plus the new identity test).
`uv run ruff check .claude/lib/qa_report.py scripts/validate_session_json.py tests/test_validate_session_json.py src/copilot-cli/lib/qa_report.py`
reported clean. A post-consensus entry documenting both fix classes was
added to `.agents/critique/ADR-099-debate-log.md` in the same commit as the
ADR prose fixes, since `git_hook_policy.py`'s `adr-review-policy` gate
requires a debate log staged alongside any non-frontmatter ADR change.

`qaCommit` moved from `3386b3cc5` to `9d8a6c287`, the last commit in this
batch that touches a non-evidence path;
`post_qa_code_changes('9d8a6c28755fbd673a2fce59d4727f0fdbf072c2', 'HEAD', ...)`
was run directly against the two session-log-only follow-up commits made
after it and confirmed to return `[]`.

## Verdict

VERDICT: PASS

The design is sound (verified by six independent reviewers across two
rounds), the implementation matches the accepted ADR exactly, the test
suite discriminates old from new behavior, and the corpus blast radius is
measured rather than assumed: one committed log changes behavior.
