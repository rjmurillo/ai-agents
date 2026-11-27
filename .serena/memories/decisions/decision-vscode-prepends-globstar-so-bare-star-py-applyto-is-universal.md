# VS Code treats bare `*.py` and `**.py` patterns as matching Python files at any depth

**Atomicity**: 90%
**Category**: Instruction budget, applyTo semantics
**Source**: Agent session sweep, sessions dated 2026-07. Sweep ids E047. State checked on main at 1be533c496 (2026-11-26).

## Question

Does a bare `*.py` applyTo pattern match only root files, or every nested file?

## Conventional answer

The instruction-budget guard classified `*`, `**.py` and `*.py` applyTo patterns as root-only. Under that model they were not language-universal.

## First-principles position

The agent read the VS Code matcher source at a pinned SHA. Bare `*`, `**` and `**/*` always attach. Any other relative pattern gets `**/` prepended, so `*.py` becomes `**/*.py` and matches nested files. The agent first agreed with a reviewer who repeated the root-only model. The source read showed the guard was wrong.

## Evidence with limits

- Read VS Code computeAutomaticInstructions.ts at pinned SHA 018354116a88 (2026-07-27).
- The guard had modeled bare `*.py` and `*` as root-only.
- A corpus census found no bare-language patterns, so the 218603-byte .py anchor did not move (2026-07-27).
- Quote: "VS Code's real semantics (verified at the pinned SHA): ... Any relative pattern not starting with `/` or `**/` gets `**/` prepended: `pattern = '**/' + pattern`. So `*.py` -> `**/*.py`"
- Limits: Source read of one VS Code file at one SHA, not a run inside VS Code. Copilot CLI and other hosts may match differently. Single session on 2026-07-27.
- State on main at 1be533c496 (2026-11-26): fixed. `scripts/validation/instruction_budget_globs.py:96-106` lists `**`, `**/*` and `*` as all-files forms, and `:178-188` prepends `**/` to relative patterns.

## Decision

Treat bare `*`, `**.py` and `*.py` applyTo values as universal for that language when sizing always-on context. Read the host matcher source before accepting a claim about glob scope.

## Related

- `.serena/memories/decision-the-instruction-budget-gate-already-exists.md`
- `.serena/memories/validation/instruction-budget-always-on-headroom.md`
