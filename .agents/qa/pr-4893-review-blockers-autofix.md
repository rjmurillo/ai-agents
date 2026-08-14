---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-14-session-14705-b71853e6d-fix-4893-review-blockers-bounded.json
qaCommit: e9e471db4c29d09fa3d986ec8ad36253a69f5eee
---

# QA Report: PR 4893 Review Blockers

## Scope

Validated bounded hook input, project and plugin definition lookup,
repository-only Claude registration, generated Copilot behavior, and
registration contract documentation.

## Results

| Validation | Result |
|---|---|
| Focused hook and registration tests | PASS, 85 tests |
| Hook generator and dispatcher tests | PASS, 398 tests and 1 skip |
| Runtime-contract and plugin-root tests | PASS, 36 tests |
| Shipped artifact and CLI E2E tests | PASS, 43 tests and 2 skips |
| Isolated plugin load smoke | PASS, 19 tests and 5 skips |
| Canonical generator drift | PASS |
| Scoped Ruff | PASS |
| Scoped mypy | PASS |
| Plugin version validator | PASS |
| Markdown lint | PASS, 12 selected files with pinned 0.23.1 |

## Edge and Inverse Coverage

- A model-less payload above 128 KiB denies in source and generated shim.
- Payload overflow above 2 MiB denies before JSON parsing.
- `CLAUDE_PROJECT_DIR` wins when payload `cwd` is a project subdirectory.
- Active Claude and Copilot plugin roots resolve matching namespaces.
- A mismatched plugin manifest and path-escaping namespace both deny.
- The repository settings command denies under Claude and exits without
  reading stdin under Copilot.

## Branch-Wide Validation

Full Windows pre-PR validation passed 49 of 51 gates before the earlier
session reports were rebound. The Windows merge-tree scratch represented the
tracked `memory_enhancement` symlink as a regular file, which changed Ruff's
import classification and produced 15 synthetic `I001` findings. The exact
merge-tree gate passed in the symlink-capable WSL clone with Ruff at 27 of 27
and all other registered ratchets below their ceilings. All four PR session
logs then passed validation. Scoped Ruff and mypy report no issues in changed
Python files.

## Verdict

PASS. The reviewed changes satisfy the requested hook contracts. Security PIV
remains required before merge because the hook reads environment-derived file
system roots.
