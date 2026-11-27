# A tracked name allowlist hid undeclared imports that share a local filename

**Atomicity**: 90%
**Category**: Dependency gates, deptry
**Source**: Agent session sweep, sessions dated 2026-11. Sweep ids E036. State checked on main at 1be533c496 (2026-11-26).

## Question

Is the dependency gate blind spot for first party names small and safely pinned?

## Conventional answer

The PR text and docstring said the known first party blind spot is small and pinned by a test.

## First-principles position

A probe contradicted that. The gate treated every tracked module name as first party. An undeclared import passed whenever an unrelated file with the same name was tracked anywhere in the repo.

## Evidence with limits

- The first party name set held about 3,300 names (2026-11-04), including github, utils, config and metrics.
- A fixture importing an undeclared `github` exited 0 whenever any github.py was tracked. It exited 1 with DEP001 once that file was removed.
- 1236 of 2409 DEP001 findings resolve from the importer's directory (2026-11-04).
- Quote from the run: "deptry: 0 finding(s) in 2 scanned files; 1 bare-name imports of tracked local modules set aside. exit=0"
- Limits: Single branch (chore/deptry-unused-deps), 2026-11-04. The original script is gone. The replacement on main was not re-probed for uninstalled third party names that collide with tracked files.
- State on main at 1be533c496 (2026-11-26): superseded. scripts/validation/check_dependencies.py no longer exists. check_unused_dependencies.py:143-161 subtracts installed third party module names from first_party_names, which closes the case for installed packages.

## Decision

A first party allowlist built from tracked filenames silences real undeclared imports. Scope it by importer path or exclude installed third party names. Probe the collision with a fixture before calling the blind spot small.

## Related

- `.serena/memories/decision-calibrate-guards-on-the-whole-corpus.md`
