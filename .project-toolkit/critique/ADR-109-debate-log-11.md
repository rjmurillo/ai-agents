# ADR Debate Log: ADR-109 recall output and diagnostics

## Summary

- **Rounds**: 2 of 10
- **Prior debate log**: [ADR-109-debate-log-10.md](ADR-109-debate-log-10.md)
- **Claims ledger**: [ADR-109-claims-ledger.md](ADR-109-claims-ledger.md)
- **Outcome**: Consensus (2 Accept)
- **Final Status**: accepted
- **Panel**: architect and critic

## Round 1 Summary

The installed hook showed computed confidence and emitted two diagnostics for a missing shim. Both reviewers confirmed the discrepancies. They flagged that nested memory IDs include directories and the title fallback uses the filename stem.

## Round 2 Summary

The record names the first body line and the filename fallback. It distinguishes search confidence from loaded metadata. It describes suppression diagnostics and leaves Claude Code's timeout behavior unverified.

| Agent | Position |
| --- | --- |
| Architect | Accept. The title, confidence, suppression, and timeout statements match the runtime sources. |
| Critic | Accept. The record distinguishes the configured timeout from unverified host behavior. |
