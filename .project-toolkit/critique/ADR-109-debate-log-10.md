# ADR Debate Log: ADR-109 amendment 2026-11-20, three decision-rigor corrections

## Summary

- **Rounds**: 1 of 10
- **Prior debate log**: [`ADR-109-debate-log-9.md`](ADR-109-debate-log-9.md)
- **Outcome**: Consensus (2 Accept)
- **Final Status**: accepted (no ADR status edit)
- **Scope**: three prose changes in the ADR-109 "Amendment 2026-11-20" section. Issue #7493.
- **Panel**: reduced panel, architect and critic. The edits correct prose and add one rejected alternative. No enforcement changes.

The `/review` decision-rigor axis raised three findings in round 1. "The hook never blocks a prompt" was unqualified, although item 6 leaves the host timeout path unverified. No latency ceiling was stated. The alternatives did not weigh shipping recall off by default.

## Round 1 Summary

### Key Issues Addressed

- The blocking claim now covers only the failure paths the dispatcher controls, and points at item 6 for the host timeout.
- Both reviewers noted that 8 seconds only stops new recall work: its clock starts after interpreter startup, and a file read already running is not interrupted. The latency sentence now names two bounds: the 8-second recall search deadline and the host's 15-second end-to-end ceiling.
- The architect asked for a source for the owner directive behind the new rejected alternative. It now cites issue #7493, section "Decision".

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept. Blocking sentence matches `invoke_dispatch_claude.py`. P2 on the latency bound and the directive source, both applied. |
| critic | Accept. Every dispatcher exit path for the recall group returns 0. P2 on the latency bound, applied. |
