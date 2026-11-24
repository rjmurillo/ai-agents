# ADR Debate Log: ADR-122 search pin renewal

## Summary

- **Rounds**: 3 of 10
- **Prior debate log**: [ADR-122-debate-log-2.md](ADR-122-debate-log-2.md)
- **Claims ledger**: [ADR-122-claims-ledger.md](ADR-122-claims-ledger.md)
- **Outcome**: Consensus after one advisor finding was fixed
- **Final status**: accepted

## Round 1 Summary

Decision D5 renewed only the two search file pins.
The analyst and advisor flagged the outdated authorization in the admission output.

## Round 2 Summary

The two records now retain D1 and D2 for the scores.
Both cite D5, its date, and the issue comment for the pin renewal.
The live assessor printed both receipts.

## Round 3 Summary

The Claude advisor delegate hit a quota limit.
Under owner decision D7, a Codex delegate took the high-level advisor seat.
It blocked on one finding.
The two renewed records set `authorizedOn` to 2026-11-22.
D1 and D2 authorized the score drops on 2026-11-20.
The fix restores 2026-11-20 on all eight records.
The D5 renewal date stays in the authorization text.
The live assessor now prints all eight admissions dated 2026-11-20.
The 91 admission tests pass.

| Agent | Position |
| --- | --- |
| Architect | Accept. The two pins match Git. All eight drops remain visible. |
| Critic | Accept. The six other records retain every field. |
| Independent thinker | Accept. The assessor still blocks when admissions are disabled. |
| Security | Accept. The matcher rejects a different blob or incomplete record. |
| Analyst | Accept after the recheck. Both renewed records carry the D5 receipt. |
| High-level advisor | Block in round 3 on the misdated `authorizedOn`. The fix applies its exact remedy. |
