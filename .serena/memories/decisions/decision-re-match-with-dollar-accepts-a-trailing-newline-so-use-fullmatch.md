# A dollar anchor under re.match can accept a trailing newline

**Atomicity**: 90%
**Category**: Input validation
**Source**: Agent session sweep, sessions dated 2026-11. Sweep ids E130. State checked on main at 1be533c496 (2026-11-26).

## Question

Did the path regex in ADR-123 reject trailing newlines?

## Conventional answer

ADR-123 said its path grammar rejected control characters.

## First-principles position

Python's `$` anchor can match before the final newline. Under `re.match`, the path prefix satisfied the regex even with a trailing newline. The grammar needed a match against the full string.

## Evidence with limits

- The probe accepted `plans/` followed by a newline (2026-11-19).
- The probe rejected a string with a newline between `a` and `b` (2026-11-19).
- Limits: One probe on one path regex and one Python version.
- State on main at 1be533c496 (2026-11-26): fixed. ADR-123:80 specifies `re.fullmatch`. `scripts/validation/skill_artifact_schema.py:24-25` applies `PATH_RE` with `fullmatch`.

## Decision

Use `re.fullmatch` or a `\Z` anchor to require the actual end of input. Test a trailing newline when verifying that a grammar rejects control characters.
