# ADR Debate Log: ADR-107 conformance row C1 citation correction

## Summary

- **Rounds**: 1
- **Outcome**: Consensus
- **Final Status**: accepted

Scope: one table cell in the ADR-107 "Conformance checks" section (class C1). The
cell said the gate runs `scripts/sync_plugin_lib.py` then `build/scripts/build_all.py`.
Issue #5790 deletes `scripts/sync_plugin_lib.py`, so the cell would cite a file that
no longer exists. `tests/validation/test_adr107_conformance_gates.py` fails CI on
that citation. The edit is a factual correction. No ADR-107 decision changes.

## Round 1 Summary

### Key Issues Addressed

- Is the new cell text accurate against the code?
- Does the edit alter a decision, or only correct a stale description?
- Does any other ADR-107 sentence still cite the deleted script as live?

### Major Changes Made

- C1 gate cell now reads: `scripts/validation/check_generated_staleness.py`, which runs
  `build/scripts/build_all.py` under `--check`, with the retired `sync_plugin_lib.py`
  step folded into it (ADR-109 B5).

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Approve. Factual correction only. The cell matches the gate docstring in `check_generated_staleness.py` (lines 36-42, 134) and ADR-109 lines 157 and 205. The class, gate script, and "Exists" state are unchanged. No other ADR-107 line cites the script as live. Non-blocking wording note on "hop", applied ("step"). |

## Decision

Accepted. The architect verified the edit against the gate docstring and ADR-109. No
other reviewer was convened because the edit carries no decision content.

### Next Steps

None. The ADR-107 text stays as edited.
