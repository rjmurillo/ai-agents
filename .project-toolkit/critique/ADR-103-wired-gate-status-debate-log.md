# ADR Debate Log: ADR-103 status update after the envelope gate landed

## Summary

- **Rounds**: 1
- **Outcome**: Consensus
- **Final Status**: accepted

Scope: two passages in ADR-103 that said `validate_envelope` has no live caller and
is wired into no gate. Issue #5299 adds the `Skill Output Envelope` pre-PR gate, so
both passages would be false. The edit updates a stale status statement. It changes
no Decision item, option, or trade-off in the ADR.

## Round 1 Summary

### Key Issues Addressed

- Does the amended text state exactly what the gate does?
- Is the edit a status update, or does it alter a decision?
- Which other ADR-103 sentences read as stale after the edit?

### Major Changes Made

- The opening paragraph now names the gate instead of saying the function has no caller.
- The Negative consequence bullet is rewritten as history plus the resolution: what the
  gate builds, what it requires, that it also checks producer error types, that it skips
  when the validator script is absent, that it checks producers and not each skill
  script's output, and that it runs in `pre_pr.py` only.
- The reference list entry for issue #5299 now says the issue is closed by the gate.
- The options table cells and the Trade-offs sentence stay as written. They describe
  the state when the ADR was accepted and remain true as history.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Approve with changes. The edit updates a stale status statement and changes no decision. Verified against `pre_pr_sequence.py` and `check_skill_output_envelopes.py`. Grep of the workflows and `lefthook.yml` found no other caller, so "pre_pr only" holds. Required two changes: fix the reference-list entry that still read as pending, and state what the gate does not do. Both applied. |

## Decision

Accepted. Verified by the architect against the code. No other reviewer was convened
because the edit carries no decision content.

### Next Steps

None.
