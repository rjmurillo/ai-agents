# Vulture whole tree name matching misses unused arguments that ruff ARG finds

**Atomicity**: 90%
**Category**: Static analysis gates, dead code
**Source**: Agent session sweep, sessions dated 2026-11. Sweep ids E016. State checked on main at 1be533c496 (2026-11-26).

## Question

Does a vulture gate catch unused imports and unused parameters in new code?

## Conventional answer

The PR said the vulture gate meant new code meets the unused code rule. Nothing in it flagged unused parameters.

## First-principles position

Vulture builds one used-names set across the whole tree. An unused import or parameter is hidden when the same name appears anywhere else. A file local detector such as ruff ARG does not have that blind spot.

## Evidence with limits

- A probe file held `import json` and `def probe_fn(path, repo_root, zzq_unique_param)`. Only `zzq_unique_param` was reported. json, path and repo_root were not (2026-11-04).
- ruff ARG over the same roots found 82 findings (65 ARG001 and 17 ARG002), where the vulture gate found 4 (2026-11-04).
- Limits: The reviewer's ruff scope omitted the gate excludes and .claude/lib, so 82 is approximate. The vulture count of 4 comes from the PR text, not a rerun. The unique import was also reported, so the probe shows a name collision gap, not total blindness.
- State on main at 1be533c496 (2026-11-26): superseded. pyproject.toml:179 says ARG is deliberately absent and that scripts/validation/check_unused_arguments.py runs ruff check with --select ARG. test_check_unused_arguments_wiring.py:147 asserts vulture is not a dependency. The vulture gate is gone.

## Decision

Use a file local detector such as ruff ARG for unused parameters. A whole tree name matching tool cannot see an unused name that another file also uses.
