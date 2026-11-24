# ADR Debate Log: ADR-122 search pin renewal D9

## Summary

- **Rounds**: 2 of 10
- **Prior debate log**: [ADR-122-debate-log-3.md](ADR-122-debate-log-3.md)
- **Claims ledger**: [ADR-122-claims-ledger.md](ADR-122-claims-ledger.md)
- **Outcome**: Consensus of the seats that ran (2 Accept)
- **Final status**: accepted

## Scope

Decision D9 renews only the two search.py head pins.
A skipped citation check no longer scores a memory as fully cited.
Both scores stay at 4.2 to 2.1 and 5.0 to 3.0.
The receipt is issue #7493 comment 7120119475.

## Round 1 Summary

The security seat accepted the change.
The matcher code did not change, and the old head pin is gone.
It noted the semgrep waiver named only two of three findings.
That wording is fixed.

The high-level advisor seat (Codex, decision D7) blocked.
A new import in validate_sync_registry.py dropped coupling from 9.0 to 8.0.
That ninth drop had no record, so the assessor exited 10.
The advisor confirmed the round 3 Block is cleared.
All eight records keep authorizedOn 2026-11-20.

## Round 2 Summary

The fix removed the new import.
The validator reads PACKAGE_SUBDIRS through its existing lib_mirror import.
The assessor exits 0 with eight admissions and no unadmitted drop.
The adapter reports WARN.
The advisor recheck ran 647 tests, and all passed.

| Agent | Position |
| --- | --- |
| Security | Accept. The matcher still demands exact blobs and scores. |
| High-level advisor | Accept in round 2. The round 1 Block is cleared. |

The architect, critic, independent thinker, and analyst seats did not run.
Their round 3 positions covered the same eight records.
This round changes only two head blobs, with identical scores.
