# A passing token budget can hide a nearly full byte budget

**Atomicity**: 90%
**Category**: Instruction budgets
**Source**: Agent session sweep, sessions dated 2026-07. Sweep ids E141. State checked on main at 1be533c496 (2026-11-26).

## Question

Does a passing token budget mean `AGENTS.md` has room for more content?

## Conventional answer

A pass from `passive_context_budget.py` was taken to mean the file had room to grow.

## First-principles position

The token check and the workspace budget check measure different units. `AGENTS.md` used 48.6% of its token budget but had 1 byte left (2026-07-30). The byte cap controlled whether an edit fit.

## Evidence with limits

- The token check reported 972 of 2000 tokens used and returned PASS (2026-07-30).
- `wc -c` returned 2999 bytes for `AGENTS.md` (2026-07-30).
- `validate_workspace_budget.py` sets a 3000-byte per-file limit. `.agents/governance/GOTCHAS.md:13` names that limit (1be533c496, 2026-11-26).
- Limits: One session on 2026-07-30. `.agents/governance/GOTCHAS.md` gives the byte cap and does not discuss the token validator.
- State on main at 1be533c496 (2026-11-26): no repo artifact. The finding concerned how to read the two checks. `AGENTS.md` measured 2994 bytes at that pin.

## Decision

Size `AGENTS.md` edits against the 3000-byte cap. Put new detail in `.agents/governance/GOTCHAS.md` when it does not fit.

## Related

- `.serena/memories/workspace/agents-md-workspace-budget.md`
- `.serena/memories/decision-the-instruction-budget-gate-already-exists.md`
