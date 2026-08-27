---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-03-fix-4899.json
qaCommit: db3a44323827e752c7f7afe0d32ba5edae25cb8d
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
`_evaluate_pr_state` appended a reason only for `BEHIND` and `BLOCKED`. A PR
with `mergeStateStatus=HAS_HOOKS` therefore classified `T1` and armed
auto-merge, though pr-autofix.md names a merge script only for `CLEAN` and
`UNSTABLE`. Fixed by allowlisting the executable merge states; see the commit
that adds this amendment.

**2. The session log's `handoffRead` evidence is wrong.**
`.agents/sessions/2026-08-15-session-03-fix-4899.json` records
`"Evidence": "No HANDOFF.md present"` for `handoffRead`. `.agents/HANDOFF.md`
does exist and is the live read-only handoff file (ADR-014). The same log
contradicts itself 67 lines later, where `handoffPreserved` records
`".agents/HANDOFF.md not modified"`; that second entry is the accurate one.

The correction is recorded here rather than in the log because the log
cannot currently be committed: `scripts/validate_session_json.py` fails it
with `endingCommit 'db3a443...' names no commit in this repository`, since
PR #5049 was squash merged and the SHA was orphaned. That failure predates
and is independent of this correction, so editing the log would trip the
`session-policy` pre-commit gate on someone else's defect. This report's
frontmatter already points at that log via `qaSessionLog`.
