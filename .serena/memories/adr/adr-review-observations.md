# Skill Observations: adr-review

**Last Updated**: 2026-02-07
**Sessions Analyzed**: 1

## Purpose

Learnings from adr-review multi-agent debate workflows. Captures corrections, patterns, and edge cases to improve future ADR reviews.

## Constraints (HIGH confidence)

- ADRs proposing shared/reusable infrastructure MUST explicitly state distribution context and target user count. Missing this context invalidates strategic review votes. (Session 1181, 2026-02-07)
  - Evidence: ADR-045 stated "no validated external demand" and "single-maintainer project" when actually targeting ~400 users for organizational distribution. High-Level Advisor voted D&C on ROI grounds based on incorrect context. Correcting to 400 users changed vote to ACCEPT.
  - User quote: "we're doing this to scale to an organization of 400 in the next 30 days. I'm not building a plugin to validate it works; I'm building it to use as a distribution."

- When a user explicitly rejects a D&C vote, investigate whether the ADR context is incorrect rather than re-arguing with the agent. D&C rejection often signals missing context, not disagreement with agent reasoning. (Session 1181, 2026-02-07)
  - Evidence: User said "high level advisor D&C is not acceptable." Root cause was factually incorrect ADR framing, not flawed advisor logic. Correcting the ADR context resolved the issue without debate.

## Preferences (MED confidence)

- Include project velocity data (commit count, session count, timeframe) when advisors question execution capacity or planning horizon. Quantitative evidence is more persuasive than qualitative arguments. (Session 1181, 2026-02-07)
  - Evidence: User said "Look at the git log to show how fast we're moving." Analysis showed 453 commits in 2 months, 1181 sessions, 580 session logs. This data was decisive in the advisor upgrading from D&C to ACCEPT.

## Edge Cases (MED confidence)

- Support re-running individual agents with corrected context mid-debate when factual errors are discovered. A "Round 2.5" pattern (single-agent re-review after context correction) is valid and avoids re-running all 6 agents. (Session 1181, 2026-02-07)
  - Evidence: After correcting ADR-045 organizational context, only the High-Level Advisor was re-run. Advisor upgraded from D&C to ACCEPT. Final tally went from 3 Accept + 3 D&C to 4 Accept + 2 D&C.

## Notes for Review (LOW confidence)

(none yet)

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-02-07 | 1181 | HIGH | ADRs must state distribution context and target user count |
| 2026-02-07 | 1181 | HIGH | D&C rejection signals incorrect context, not bad reasoning |
| 2026-02-07 | 1181 | MED | Include velocity data to counter execution capacity concerns |
| 2026-02-07 | 1181 | MED | Single-agent re-review (Round 2.5) valid for context corrections |

## Related

- [debate-001-multi-agent-adr-consensus](debate-001-multi-agent-adr-consensus.md) - Base protocol
- [pr-review-observations](pr-review-observations.md) - Related review patterns
- ADR-045 debate log: `.agents/critique/ADR-045-debate-log.md`
