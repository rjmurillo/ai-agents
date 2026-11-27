# Import linter skips scripts directories without an __init__.py, so tests imports pass unchecked there

**Atomicity**: 90%
**Category**: Static analysis gates, import contracts
**Source**: Agent session sweep, sessions dated 2026-11. Sweep ids E015. State checked on main at 1be533c496 (2026-11-26).

## Question

Does a passing import-linter tests contract prove that scripts never import tests?

## Conventional answer

The PR body and CONTRIBUTING said the static import graph covers every module, and that scripts never import tests.

## First-principles position

grimp reads only directories that hold an __init__.py. Directories without one report 0 modules, so the contract cannot see imports there. A passing contract proves nothing about those trees.

## Evidence with limits

- grimp reported 0 modules for scripts.ci, scripts.eval, scripts.testing, scripts.memory, scripts.security, scripts.workflows and scripts.dev, and 235 for scripts.validation (2026-11-05).
- 284 of 719 scripts .py files sit in the unreachable directories (2026-11-05).
- A planted `import tests.conftest` in scripts/ci left 4 contracts KEPT with exit 0. The same line in scripts/validation went BROKEN.
- Limits: One import-linter and grimp version at 2026-11-05. The 719 count is all scripts .py files, not only shipped ones. The probe ran in a throwaway copy.
- State on main at 1be533c496 (2026-11-26): fixed as documentation. CONTRIBUTING.md:918 says grimp reads only directories that hold an __init__.py, so a tests import under scripts/ci or scripts/eval escapes the contracts. scripts/ci/__init__.py is still absent.

## Decision

A passing import-linter contract proves nothing about a directory with no __init__.py. Probe each contract with a planted violation in every covered tree.
