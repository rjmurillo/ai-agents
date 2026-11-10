# ADR-041 Debate Log 3: exit 1 in the /review local fallback

**ADR**: `.project-toolkit/architecture/ADR-041-codeql-integration.md`
**Amendment**: "Amendment 2026-11-09: Let /review read CodeQL results as an explicit caller"
**Rules file**: `.project-toolkit/analysis/adr-041-review-caller-rules.md`
**Prior debate log**: `.project-toolkit/critique/ADR-041-debate-log-2.md` (closed by consensus in round 3)
**Review date**: 2026-11-10
**Protocol**: adr-review, reduced panel. The change corrects one outcome rule
inside the amendment. It touches no executable enforcement and no rule another
gate reads, so the reduced panel applies.
**Participants**: architect, critic

## Summary

PR #7182 review thread `PRRT_kwDOQoWRls61i3FK` (Cursor Bugbot, medium) found a
contradiction in the local fallback rule accepted in debate log 2. The rule
runs the wrapper with `--ci`, which exits 1 when the scan finds issues (ADR-035,
`codeql-scan` exit-code table). The same rule mapped every exit except a clean 0
to `SKIPPED`. A local scan that found issues could therefore never report them,
which contradicts the amendment's own review-by clause that counts "a `CLEAN` or
findings result".

## Round 1 Summary

### Key Issues Addressed

- **P1:** exit 1 with fresh SARIF must be a findings outcome, not `SKIPPED`.

### Major Changes Made

- Rules file: the step passes the language set explicitly with `--languages`,
  mapped from the diff's file types; an empty set is `SKIPPED`. With fresh SARIF
  for each requested language, exit 0 with zero results is `CLEAN` and exit 1
  with at least one result is `FINDINGS`, read from those SARIF files. Any
  mismatch between exit code and result count is `SKIPPED`.
- ADR summary item 3 states the same mapping.

### Review findings folded in

- **P2 (architect, critic):** Python exits 1 on any uncaught exception, and the
  delegate catches only `RuntimeError`
  (`.codeql/scripts/invoke_codeql_scan.py:532-534`). Exit 1 alone could report
  `FINDINGS` with empty SARIF. Fixed by requiring the result count to agree with
  the exit code.
- **P2 (critic):** under `--ci` the delegate never prints its detected language
  list, so "each detected language" was untestable. Fixed by passing the
  language set explicitly.
- Verified: the wrapper defines 0 success, 1 findings in CI mode, 2 config
  invalid, 3 execution failed (`invoke_codeql_scan.py:11-14`); the delegate
  returns 1 only from its findings path (`:521-528`). No path to a false
  `CLEAN` was found.

### Agent Positions

| Agent | Position | Basis |
|---|---|---|
| architect | Accept | Matches the wrapper exit codes; P2 folded in |
| critic | Disagree-and-Commit | No false CLEAN; two P2s folded in |

### Outcome

Consensus reached in round 1 under the reduced panel: 1 Accept, 1
Disagree-and-Commit. The correction is accepted and closes PR #7182 thread
`PRRT_kwDOQoWRls61i3FK`.
