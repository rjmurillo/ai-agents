# CI pinned to Python 3.14 hides import errors on older supported versions

**Atomicity**: 90%
**Category**: CI interpreter floor
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E103. State checked on main at 1be533c496 (2026-11-26).

## Question

Does green CI on Python 3.14 show that a package works on Python 3.11?

## Conventional answer

A green CI run was taken as proof that the package met its declared Python 3.11 minimum.

## First-principles position

After a lint pass, `semantic_hooks.core` referred to classes before they were defined. Python 3.12 and 3.13 evaluated those annotations during import and raised `NameError`. Python 3.14 defers annotation evaluation under PEP 649, so the import passed there.

## Evidence with limits

- Importing `semantic_hooks.core` raised `NameError` on Python 3.12 and 3.13 (2026-08-04). The same import passed on 3.14.
- The import failure caused 3 test collection errors on 2026-08-04.
- Limits: The probe covered one module on 2026-08-04. Python 3.11 shares the earlier annotation behavior, but the session did not run it.
- State on main at 1be533c496 (2026-11-26): still wrong. `packages/semantic-hooks/src/semantic_hooks/core.py:124` and `:156` use unquoted forward references without `from __future__ import annotations`. `packages/semantic-hooks/pyproject.toml:11` declares Python >=3.11. No workflow tests Python 3.11 through 3.13.

## Decision

Run an import test on the oldest supported Python version. Quote forward references or defer annotation evaluation. The wrong state on main is tracked in the GitHub issue linked from the pull request that added this memory.

## Related

- `.serena/memories/session-2026-06-10-latent-issues-review.md`
