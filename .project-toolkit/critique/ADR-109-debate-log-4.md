# ADR Debate Log: ADR-109 line 96 citation into ADR-107

## Summary

- **Rounds**: 1 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-109-debate-log-3.md`
- **Outcome**: Consensus
- **Final Status**: accepted (the edit changes no ADR status)
- **Scope**: one line number on ADR-109 line 96.
- **Panel**: reduced panel, architect and critic. The edit is prose only.

ADR-109 line 96 cites ADR-107 line 663 for the Related Decisions bullet that reads
"`accepted` 2026-09-11): widens". On `origin/main` at `7dab88e5c` (2026-11-20), line 663 is an
MCP agent bullet. The quoted bullet sits at line 725. The citation was already stale.

The same branch adds three lines to ADR-107 Related Decisions (see
`.project-toolkit/critique/ADR-107-debate-log-3.md`). The quoted bullet moves to line 728. The
`Citation Freshness (reverse pass)` gate then blocks the branch. Its `_quote_moved_outside` check
in `scripts/validation/citation_reverse_judge.py` flags a quoted line that changed number. It does
not check that the quote sat inside the cited range at base. The owner chose to fix the citation
rather than reshape the ADR-107 text.

## Round 1 Summary

### Key Issues Addressed

- Is line 728 the right target? Yes. Both seats read the quoted text at ADR-107 line 728.
- Does the edit change an ADR-109 decision or its four-site amendment meaning? No. Only the
  line number changes.
- Do other ADR-109 citations into ADR-107 break? No. Line 95 cites ADR-107 line 63, above both
  ADR-107 edits. Six other ADR-107 mentions carry no line number.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept. Quote verified at ADR-107 line 728. The old target at `7dab88e5c` was stale. Land both ADR edits in one PR, since 728 holds only with the ADR-107 change. |
| critic | Accept. Line 728 correct. No other ADR-109 citation breaks. Noted the gate prints "0 already stale at the merge base" for this citation. The cause: the quote-move check records a finding before the base-debt tally counts it. |

## Decision

Accepted by both seats. The two ADR edits ship in one commit series on one PR.

### Next Steps

The gate defect is flagged in the pull request body for the owner. This change does not fix it.
