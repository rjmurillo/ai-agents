# Reading git output as text can turn a carriage return into a record break

**Atomicity**: 90%
**Category**: Git output parsing
**Source**: Agent session sweep, sessions dated 2026-08 to 2026-11. Sweep ids E082, E107. State checked on main at 1be533c496 (2026-11-26).

## Question

Can a carriage return in a commit subject or file path forge a record when git output is read in text mode?

## Conventional answer

The orphaned commit scanner relied on a record start regex to reject forged records. A separate review blamed `str.splitlines` in a path verifier. Its docstring said removing the check would let invalid input pass.

## First-principles position

Text mode rewrites a CR to LF in the decoder, before any splitter or anchor runs. A subject holding a CR then looks like two records. Anchoring on a record-start regex fails, and so does blaming `splitlines` alone. Removing the guard gave exit 1 with a fabricated key, not a false clean. Reading bytes avoids the rewrite.

## Evidence with limits

- E082 (2026-11-04): A Git probe put a carriage return in a commit subject. The scanner returned two records and flagged neither.
- E082: The control subject triggered the warning for removing test definitions.
- E107 (2026-08-05): CPython 3.14.6 read carriage returns as line feeds with `text=True`. Byte mode kept the original bytes.
- E107: With the guard removed, the verifier returned exit 1 with a fabricated key. It did not report a clean result.
- Limits: E082 used one repo on Linux. E107 used one CPython version on Linux. Its exit 1 came from a PR branch.
- State on main at 1be533c496 (2026-11-26): fixed for E082. `scripts/github_core/orphaned_commits.py:126` reads bytes to preserve carriage returns in subjects.
- State on main at 1be533c496 (2026-11-26): no repo artifact for E107's guard or docstring. `src/claude/skills/merge-resolver/scripts/verify_no_conflict_markers.py:69` uses `text=True`. Lines 92 and 123 still call `splitlines()`.

## Decision

Read git output as bytes and split on LF when a path or subject can hold a CR. Test the forgery with CR and other line-break characters in the field, not only the delimiter. Do not blame `splitlines` alone. Measure what a removed guard does before writing its docstring.
