# Clearing pytest addopts caused failures that the default run did not reproduce

**Atomicity**: 90%
**Category**: Local test reproduction
**Source**: Agent session sweep, sessions dated 2026-07. Sweep ids E136. State checked on main at 1be533c496 (2026-11-26).

## Question

Does a manual pytest run with cleared options reproduce a pre-push failure?

## Conventional answer

The manual pytest failures were treated as existing test failures that blocked the push.

## First-principles position

The manual command dropped `--import-mode=importlib` by clearing `addopts`. That changed which modules the reachability tests patched. Pytest passed with the default options. The type check was the actual push blocker.

## Evidence with limits

- Clearing `addopts` broke 3 reachability tests (2026-07-27).
- The hook's default pytest run reported 15,419 passed and 0 failed (2026-07-27).
- The `python-type-check` job reported 18 mypy errors (2026-07-27).
- Limits: One session. The mypy errors came from the session's own changes. The record does not name the three tests that failed with modified options.
- State on main at 1be533c496 (2026-11-26): no repo artifact. The override was local. `pyproject.toml:115` still sets `--import-mode=importlib` in `addopts`.

## Decision

Reproduce failures with the repository's default pytest options or run the hook itself. Read the hook's job status to identify which check blocked the push.
