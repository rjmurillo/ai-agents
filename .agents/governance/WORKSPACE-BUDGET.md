# Workspace Budget

Non-obvious facts about the workspace byte-gate that save debugging time.
Split out of `GOTCHAS.md` so byte-gate detail stays independently retrievable.

## Byte-gate ceilings (always-on files)

These files are measured by `scripts/validate_workspace_budget.py` when root
instruction files or the validator change. Each file has a ceiling. Exceeding
it fails the required validation.

| File | Ceiling | Ratchet? | Notes |
|---|---|---|---|
| `AGENTS.md` | 4800 bytes | no | Shared gotchas and routing; 4721 bytes accepted by issue #4880 |
| `CLAUDE.md` | 4800 bytes | no | Claude-specific overlay |
| `.claude/CLAUDE.md` | 4800 bytes | no | Path-local Claude overlay |
| `.github/copilot-instructions.md` | 1400 bytes | yes | Copilot-specific overlay; 1294 bytes accepted by issue #4880 |

**Standard files** (no ratchet) also share a combined pool: `TOTAL_BUDGET_BYTES = 6100`.
Files with a ratchet are measured only by their individual ceiling.

**To lower a ratchet**: trim the file content, then update `FILE_CEILING_BYTES`
in `scripts/validate_workspace_budget.py` to the new measured size. Never raise
a ceiling without recording the reason in the same change.

## The shared total only covers standard files

`TOTAL_BUDGET_BYTES = 6100` applies to `AGENTS.md + CLAUDE.md + .claude/CLAUDE.md`
only. Adding a ratchet file to that sum would yield a meaningless constraint
because the ratchet file already has its own ceiling.

## An empty WORKSPACE_FILES disables the gate silently

`test_workspace_files_nonempty` guards this. If you see that test failing, the
constant was emptied somewhere and every per-file assertion is vacuously true.

## Gate location

`tests/test_workspace_limits.py` runs via the standard `pytest` suite. It imports
constants from `scripts/validate_workspace_budget.py` directly, so the test and
the enforcer always agree (fixed by issue #3951).
