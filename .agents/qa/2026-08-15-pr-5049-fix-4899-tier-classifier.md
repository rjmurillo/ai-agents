---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-03-fix-4899.json
qaCommit: fd1e1cde8834d1b85e209da3397bbb7acf5fb43b
---
# QA Report: fix(pr-autofix) define total tier classifier

## Verdict: PASS

## Test Results

| Suite | Tests | Result |
|-------|-------|--------|
| tests/test_test_pr_merge_ready.py | 92 | PASS |
| tests/test_subprocess_text_encoding.py | 391 | PASS |

## Coverage

17 new tests exercise the tier classifier: all tier values, edge cases, bot flag, integration.

## Risk Assessment

- Low risk: additive function, no existing behavior changed
- Backward compatible: new Tier field in output JSON, consumers not yet reading it
- Pre-existing fix: consume_pytest_signal.py encoding is a one-line addition

## Amendment: two claims above and in the session log were wrong

Recorded rather than rewritten, so the original assessment and its
correction both stay readable. The issue #4899 reopen comment
(id 5303223362, 2026-08-15) named both.

**1. "Low risk: additive function, no existing behavior changed" is wrong.**
The `Tier` field is not inert. `.claude/commands/pr-autofix.md` reads it in
two blocking decisions: the auto-merge disarm gate and the round-cap gate,
both in its Step 2.5. A `T1` classification arms the auto-merge path. So the
change did alter existing behavior, on the path with the largest blast
radius in that command, and the risk line understated it in the one place a
reviewer would look. The bullet immediately below it, "consumers not yet
reading it", is the same error stated as fact.

That mattered concretely. The classifier returned `T1` for any result with
`CanMerge=true`, and `CanMerge` was `len(reasons) == 0` while
`_evaluate_pr_state` appended a reason for `BEHIND` and `BLOCKED` (as well as
non-open state, draft status, `CONFLICTING`, and `UNKNOWN`), so any
mergeStateStatus value outside that set classified `T1` and armed auto-merge. A PR reporting
`mergeStateStatus=A_STATE_GITHUB_ADDS_LATER`, the placeholder
`tests/test_test_pr_merge_ready.py:1553` carries for a state GitHub adds later,
has no merge row in pr-autofix.md and reached the merge tier anyway.
`HAS_HOOKS` is not that example: the allowlist admits it and pr-autofix.md
routes it down the `CLEAN` merge path. Fixed by allowlisting the executable
merge states; see the commit that adds this amendment.

**2. The session log's `handoffRead` evidence is wrong.**
`.agents/sessions/2026-08-15-session-03-fix-4899.json` records
`"Evidence": "No HANDOFF.md present"` for `handoffRead`. `.agents/HANDOFF.md`
does exist and is the live read-only handoff file (ADR-014). The same log
contradicts itself 67 lines later, where `handoffPreserved` records
`".agents/HANDOFF.md not modified"`; that second entry is the accurate one.

Corrected in the log itself: `handoffRead.Evidence` now reads
`Read .agents/HANDOFF.md`, matching the accurate `handoffPreserved` entry.

An earlier draft of this section claimed the log could not be committed,
because `scripts/validate_session_json.py` failed it with `endingCommit
'db3a443...' names no commit in this repository`: PR #5049 was squash merged
and the branch SHA was orphaned. That blocker did not hold on inspection.
`git log origin/main --oneline --grep "#5049"` names the squash commit,
`fd1e1cde8834d1b85e209da3397bbb7acf5fb43b`, and re-pointing both the log's
`endingCommit` and this record's `qaCommit` at it clears the validator. Both
edits ship with the correction above.
