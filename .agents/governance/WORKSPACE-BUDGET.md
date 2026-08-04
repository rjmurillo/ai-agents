# Workspace Budget

Non-obvious facts about the workspace byte-gate that save debugging time.
Split out of `GOTCHAS.md` to keep that file under the 500-line taste ceiling.

## Byte-gate ceilings (always-on files)

These files are measured by `scripts/validate_workspace_budget.py` on every CI
run. Each file has a ceiling. Exceeding it blocks the push.

| File | Ceiling | Ratchet? | Notes |
|---|---|---|---|
| `AGENTS.md` | 3000 bytes | no | Standard; 2999 bytes as of 2025-07-30 (one byte of headroom) |
| `CLAUDE.md` | 3000 bytes | no | Standard |
| `.claude/CLAUDE.md` | 3000 bytes | no | Standard |
| `.github/copilot-instructions.md` | 6351 bytes | yes | Non-regression ratchet seeded at 6351 bytes (2025-07-30, issue #3991). Target: reduce to 3000 after moving the Gotchas section to `.agents/governance/` (issue #3952). |

**Standard files** (no ratchet) also share a combined pool: `TOTAL_BUDGET_BYTES = 6600`.
Files with a ratchet are measured only by their individual ceiling.

**To lower a ratchet**: trim the file content, then update `FILE_CEILING_BYTES`
in `scripts/validate_workspace_budget.py` to the new measured size. Never raise
a ceiling without recording the reason in the same change.

## The shared total only covers standard files

`TOTAL_BUDGET_BYTES = 6600` applies to `AGENTS.md + CLAUDE.md + .claude/CLAUDE.md`
only. Adding a ratchet file to that sum would yield a meaningless constraint
because the ratchet file already has its own ceiling.

## An empty WORKSPACE_FILES disables the gate silently

`test_workspace_files_nonempty` guards this. If you see that test failing, the
constant was emptied somewhere and every per-file assertion is vacuously true.

## Gate location

`tests/test_workspace_limits.py` runs via the standard `pytest` suite. It imports
constants from `scripts/validate_workspace_budget.py` directly, so the test and
the enforcer always agree (fixed by issue #3951).
