# A typed only skill reference rule would drop most real skill references

**Atomicity**: 90%
**Category**: Validator design, orphan refs
**Source**: Agent session sweep, sessions dated 2026-07. Sweep ids E005. State checked on main at 1be533c496 (2026-11-26).

## Question

Would extracting only typed skill references cut orphan-ref false positives without losing real references?

## Conventional answer

Issue 3637 proposed direction 1: extract only typed skill references to cut false positives in orphan-ref-validator.

## First-principles position

The data refutes direction 1. Almost all real skill references are untyped. A typed only rule would drop 57 of 68 true positives and keep 22 typed findings that were never a skill (measured 2026-07-28).

## Evidence with limits

- Measured 2026-07-28 over .serena, .agents, .claude and docs: 1790 skill_name findings, 33 typed and 1757 untyped.
- Ever-a-skill true positives: 68 in total, 11 typed and 57 untyped. Ever-a-skill false: 22 typed and 1700 untyped.
- Quote from the run: "ever-a-skill=True: typed= 11 untyped= 57 | ever-a-skill=False: typed= 22 untyped= 1700"
- Limits: One commit, measured 2026-07-28. Ever-a-skill labels come from the git history of skill directories.
- State on main at 1be533c496 (2026-11-26): superseded. scan.py:435 now reads `candidate = (is_typed and in_retired) if typed_only else (is_typed or in_retired)`, a union rule outside .serena memories.

## Decision

Do not narrow orphan-ref detection to typed references only. Bound the candidate set by the retired-skill allowlist and accept typed claims as extra evidence.

## Related

- `.serena/memories/decision-orphan-ref-scope-serena-memories.md`
