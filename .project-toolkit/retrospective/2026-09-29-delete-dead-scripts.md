# Retrospective: delete-dead-scripts

## Session Info
- **Date**: 2026-09-29
- **Agents**: implementer
- **Task Type**: Cleanup
- **Outcome**: Success

## What Happened
- Issue #5585 listed 18 scripts with no caller outside their own tests.
- A search for path strings, dotted imports, and bare imports over every tracked file outside history records confirmed all 18.
- Deleted the 18 modules and 13 dedicated test files.
- Edited five test files that also covered live code, and one string fixture.
- Removed two mypy override entries from `pyproject.toml`.
- `build_all.py` pruned the two `src` copies of `discourse_traversal.py`. It did not prune the binplaced `.claude/lib` copy, so that file was deleted by hand.
- Lowered the taste baseline from 555 to 544.

## Learning
- Deleting a module means checking its plugin mirrors and test guards too.
