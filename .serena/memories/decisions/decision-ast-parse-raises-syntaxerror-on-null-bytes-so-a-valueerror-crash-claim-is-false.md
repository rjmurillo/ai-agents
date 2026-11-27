# Python 3.14 raises SyntaxError for null bytes in ast.parse

**Atomicity**: 90%
**Category**: Review claim verification
**Source**: Agent session sweep, sessions dated 2026-07. Sweep ids E139. State checked on main at 1be533c496 (2026-11-26).

## Question

Does a null byte in Python source bypass the verifier's `SyntaxError` handler?

## Conventional answer

A review claimed that `ast.parse` would raise `ValueError` and bypass the `SyntaxError` handler.

## First-principles position

On Python 3.14, `ast.parse` raised `SyntaxError` for source containing a null byte. The verifier caught it and returned a `VerificationResult`. The claimed crash did not occur on the pinned interpreter.

## Evidence with limits

- A direct `ast.parse` call on source with a null byte raised `SyntaxError` (2026-07-30).
- The end-to-end verifier returned a `VerificationResult` (2026-07-30).
- Limits: The session used Python 3.14. A separate local parser check used 3.15. The reported regex timing result lacked a matching tool output in the record.
- State on main at 1be533c496 (2026-11-26): no repo artifact is wrong. `scripts/memory_enhancement/verification.py:327` catches `SyntaxError`.

## Decision

Probe a reported parser crash on the pinned interpreter before adding an exception handler.
