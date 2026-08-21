---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-21-session-99927-9e1ebd2b8-adr-099-session-qa-binding.json
qaCommit: 06fa514b552933b3bb5003dd56a18db657fc65e6
---

# ADR-099 Session QA

## Scope

Code change: `.claude/lib/qa_report.py` (`QaBinding` gains `inconsistency`,
`session_qa_binding()` replaces its field-equality raise with the diagnostic),
mirrored byte-identical to `src/copilot-cli/lib/qa_report.py`, and
`scripts/validate_session_json.py` (`validate_qa_report_evidence()` surfaces
the diagnostic into `result.warnings`). Test change:
`tests/test_validate_session_json.py` (`test_rejects_qa_commit_disagreement`
replaced, five new unit cases, one wiring test). Unrelated red-CI fixes
carried on the same branch: `tests/ci/test_validate_vendor_provenance.py`
(stale setup-uv SHA pin) and `.github/workflows/pytest.yml` (pip pin moved
past PYSEC-2026-3721). Everything else on this branch is ADR-099 and its
debate log, both documentation.

## Test Results

| Command | Result |
|---|---|
| `uv run pytest tests/test_validate_session_json.py -q` | 379 passed |
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

## Verdict

VERDICT: PASS

The design is sound (verified by six independent reviewers across two
rounds), the implementation matches the accepted ADR exactly, the test
suite discriminates old from new behavior, and the corpus blast radius is
measured rather than assumed: one committed log changes behavior.
