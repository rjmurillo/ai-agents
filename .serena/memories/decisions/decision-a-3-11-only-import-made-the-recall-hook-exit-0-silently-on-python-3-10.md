# The recall hook exited 0 without recalling anything on Python 3.10

**Atomicity**: 90%
**Category**: Hook contract
**Source**: Agent session sweep, sessions dated 2026-11. Sweep ids E152. State checked on main at 1be533c496 (2026-11-26).

## Question

Does a syntax check prove the recall hook imports on the oldest accepted Python version?

## Conventional answer

ADR item 5 required the recall hook and its dependencies to import on Python 3.10 and later. The syntax check was treated as proof.

## First-principles position

The hook depended on `datetime.UTC`, which Python added in 3.11. On 3.10 it failed during import, warned on stderr, and exited 0 with no stdout. A syntax check cannot detect a missing import at runtime.

## Evidence with limits

- With uv and Python 3.10.20, the hook returned 0 with no stdout and a warning about the missing UTC import (2026-11-20).
- The imports appeared at `confidence.py:9`, `models.py:12`, and `serena_integration.py:12` (2026-11-20).
- Limits: One interpreter tested in one session on 2026-11-20. `validate_python_syntax.py` checks syntax only.
- State on main at 1be533c496 (2026-11-26): fixed. `scripts/memory_enhancement/confidence.py:9` uses `datetime.timezone`. `tests/hooks/test_memory_recall_python_floor.py` checks the Python floor.

## Decision

Run the shipped hook with its dependencies on the oldest interpreter the launcher accepts.

## Related

- `.serena/memories/decisions/decision-ci-pinned-to-python-3-14-hides-import-errors-at-the-declared-3-11-floor.md`
