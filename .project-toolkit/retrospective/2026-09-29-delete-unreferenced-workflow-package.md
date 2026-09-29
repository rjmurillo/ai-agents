# Retrospective: delete-unreferenced-workflow-package

## Session Info
- **Date**: 2026-09-29
- **Agents**: implementer
- **Task Type**: Cleanup
- **Outcome**: Success

## What Happened
- Issue #5587 named `scripts/workflow/` as an engine with no caller.
- A repository search for imports and path strings found only the package, its three test files, one packaging entry, two doc lines, and history records.
- Deleted the six modules and three test files (88 tests).
- Dropped `scripts.workflow*` from the `pyproject.toml` include list. The `scripts*` glob still covers every remaining package.
- Fixed the stale "pipeline executor" line in `scripts/AGENTS.md` and its generated context copy.
- Lowered the taste baseline from 555 to 554 with the ratchet `--update` step.

## Learning
- An engine with tests but no caller still costs CI time and reader attention.
