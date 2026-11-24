# ADR Debate Log: ADR-071 recall diagnostics

## Summary

- **Rounds**: 1 of 10
- **Prior debate log**: [ADR-071-debate-log.md](ADR-071-debate-log.md)
- **Claims ledger**: [ADR-071-claims-ledger.md](ADR-071-claims-ledger.md)
- **Outcome**: Consensus (2 Accept)
- **Final Status**: accepted
- **Panel**: architect and critic

## Round 1 Summary

The reserved recall group can report more than one diagnostic for a failure. The prose now reflects the runtime. The exit policy stays in scope for issue #7493.

| Agent | Position |
| --- | --- |
| Architect | Accept. The reserved group exits zero and reports failures on stderr. |
| Critic | Accept. Focused dispatch and runtime tests passed. |
