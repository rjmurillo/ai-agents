# ADR Debate Log: ADR-071 carve-out relocation and ADR-109 recall bounds

## Summary

- **Rounds**: 1 of 10
- **Prior debate log**: [`ADR-109-debate-log-5.md`](ADR-109-debate-log-5.md)
- **Outcome**: Consensus (1 Accept, 1 Disagree-and-Commit, 0 Block)
- **Final Status**: accepted (the edits change no ADR status)
- **Scope**: prose in ADR-071 and ADR-109 after the closed debate in log 5. Issue #7493.
- **Panel**: reduced panel, architect and critic. The edits move and add prose. The enforcement they describe was reviewed in log 5 and in commit `ea4eb210b`.

The log-5 version of ADR-071 added a separate "2026-11-20 amendment" section. That took the file from 850 to 867 lines. The ADR lifecycle size-cap ratchet (`tests/validation/test_check_adr_lifecycle.py`) counts 50-line steps above a 500-line cap, and `main` sits at 850, so the branch gained a step and failed. The section was removed. Its contract now sits on ADR-071's Decision item 5 carve-out line, and ADR-109's 2026-11-20 amendment, item 6, holds the full text. ADR-071 is back to 850 lines.

ADR-109's trust-boundary list also gained one bullet for work that closed the security seat's log-5 debt: a 50-candidate cap and an 8-second recall deadline.

## Round 1 Summary

### Key Issues Addressed

- Does ADR-071 still record what the architect's log-5 P1 asked for? Yes: the Status line (ADR-071:20), the Decision item 5 carve-out (:701), the paragraph near :248, and the `--advisory` refusal sentence (:654).
- Is anything from the removed section now recorded nowhere? The critic found one item: the runtime test citation for `tests/hooks/test_plugin_memory_recall_runtime.py`.
- Do the new ADR-109 claims match the code? `MAX_CANDIDATES = 50` at `scripts/memory_enhancement/search.py:26`. `RECALL_DEADLINE_SECONDS = 8.0` at `scripts/memory_enhancement/hooks/user_prompt_submit_memory.py:102`. Subprocess timeouts shrink to the time left at `search.py:150-155`, and citation checks stop at `search.py:379`.
- Dangling references to the removed section: none outside the closed log 5.

### Major Changes Made

- ADR-109's Verification paragraph now cites `tests/hooks/test_plugin_memory_recall_runtime.py`, which is the `generated-artifacts.md` MUST 2 evidence.
- The bounds bullet cites `tests/test_memory_search_bounds.py`.
- The bounds bullet now says the deadline stops new work, not running work. A file read already running is not interrupted (`verification.py:170,228`).

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept. All log-5 P1 items still recorded in ADR-071. P2 wording on the deadline, applied. |
| critic | Disagree-and-Commit. Two P2 citation gaps, both applied. No P0 or P1. |

### Next Steps

None for these records. The log-5 debt list is unchanged, except that the uncapped candidate scoring and the missing overall deadline are now closed.
