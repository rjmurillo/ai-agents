# Retrospective Accuracy Requirements

**Last Updated**: 2026-04-10
**Sessions Analyzed**: 1

## Constraints (HIGH confidence)

- Retrospective agents must receive raw friction data (turn count, steering events, failures), not outcome summaries. Sanitized retros are worthless. (Session 2, 2026-04-10)
  - Evidence: First retrospective said "pivots: none" and "efficiency: ~50%". Real data: 3+ sessions, 4 user steering corrections, ~25% efficiency. User said "be self critical" and "I don't think it's quite accurate."
  - Fix: Include in retrospective agent prompt: actual turn count, number of user corrections, number of failed commands, number of fix iterations

- Learnings proposed in retrospectives must be persisted to Serena immediately, not left as text in the retro artifact. Otherwise they are lost to new agent sessions. (Session 2, 2026-04-10)
  - Evidence: User noted "learnings were proposed in the retrospective but then not persisted to Serena, so they will be lost to a new agent session"