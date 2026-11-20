# ADR Debate Log: citation refresh in ADR-100, ADR-102, and ADR-109

## Summary

- **Rounds**: 3 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-109-debate-log-4.md` (closed)
- **ADRs covered**: ADR-100, ADR-102, ADR-109
- **Outcome**: Consensus
- **Final Status**: unchanged (no ADR status edit)

This branch deleted lines from `git_hook_policy.py` and moved other cited files.
The citation reverse pass then flagged seven ADR citations as stale.
Round 3 covers ten ADR-102 References lines that the gate checked next to the edit.
The edit touches citations only, so the reduced panel ran (architect and critic).
No decision text, status, or rule changed.

## Round 1 Summary

### Votes

| Agent | Vote |
|-------|------|
| architect | Block |
| critic | Block |

### Key Issues

| # | Issue | Pri | Resolution |
|---|-------|-----|------------|
| 1 | ADR-100 lines 45, 256, and 436 cite a commit-limit gate that no longer exists. The refreshed numbers pointed at unrelated code. | P0 | Original numbers restored. Each line carries a reasoned ignore marker that names the revision it describes. |
| 2 | ADR-102 lines 221 and 355 cited debate-log placeholder code at `:1949`. | P0 | Both now cite `git_hook_policy.py:2774`, which passes the mode flags. |
| 3 | ADR-100 line 256 also cites `:6727`, which is stale. | P1 | The line marker covers it and names `72f0e6309`. |
| 4 | ADR-109 B1 could cite `validate_install_parity.py:149` instead of a marker. | P2 | Kept the marker. The row records the regex B1 rewrote, which no longer exists. |
| 5 | The reverse pass follows moved text, not meaning, so it can "fix" a dead citation. | P2 | Out of scope here. Flagged in the PR body. |

## Round 2 Summary

### Votes

| Agent | Vote |
|-------|------|
| architect | Accept |
| critic | Accept |

### Key Issues

| # | Issue | Pri | Resolution |
|---|-------|-----|------------|
| 1 | The ADR-100 markers named the wrong revision. | P2 | Each marker now names its revision. Lines 45 and 436 match `ba541c21f` (2026-08-20). Line 256 matches `ba541c21f` and `72f0e6309` (2026-09-08). |

### Claims Checked

| Claim | Result |
|---|---|
| `git_hook_policy.py:2774` passes `--pre-commit` and `--existing-log` | VERIFIED |
| `23ad6e429` (2026-09-22) deleted the commit-limit gate | VERIFIED |
| `3487d2f69` (2026-08-21) removed the bypass-label comment | VERIFIED |
| `ba541c21f` holds `:6055-6070`, `:6122`, and `:5604` as cited | VERIFIED |
| `72f0e6309` holds `_check_commit_limit` at `:6727` | VERIFIED |
| ADR-109 B4 `official-hook-contracts.md:316-319` matches its claim | VERIFIED |
| The word diff changes no decision text | VERIFIED |

## Round 3 Summary

Editing ADR-102 line 355 brought its neighbours, lines 350-358, under the strict anchor check.
Those citations were already stale on main.

### Votes

| Agent | Vote |
|-------|------|
| architect | Disagree-and-Commit |
| critic | Disagree-and-Commit |

### Key Issues

| # | Issue | Pri | Resolution |
|---|-------|-----|------------|
| 1 | Line 350 cited `qa_report.py:142-182`; `session_qa_binding` is now `:145-203`. | P1 | Now `:145-203`. A reasoned marker notes that `:173-177` is the raise this ADR deleted. |
| 2 | Line 351 cited `:185-209`; `validate_qa_report` is now `:206-227`. | P1 | Now `:206-227`. |
| 3 | Line 353 cited the fallback, not the live-HEAD resolution. | P1 | Now `validate_session_json.py:1663-1665`. |
| 4 | Line 354 stopped before the error append. | P2 | Now `:691-728`. |

### Claims Checked

| Claim | Result |
|---|---|
| `validate_session_json.py:950-1018` is `validate_qa_report_evidence` | VERIFIED |
| `session_scope.py:391-416` is `committed_session_validation_modes()` | VERIFIED |
| Schema `:159-163` is the `commitHead` block | VERIFIED |
| Extractor `:843-844` is the two-line comment | VERIFIED |
| The diff changes no decision text | VERIFIED |

## Dissent

Both seats disagreed and committed in round 3 on the issues above. All issues were then fixed as listed.
