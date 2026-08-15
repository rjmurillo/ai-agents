# Retrospective: Issue #4938 Model Pin Removal

**Date**: 2026-08-14
**Issue**: #4938
**Branch**: fix/4938-remove-copilot-model-pins

## Learnings Captured

1. **Display-name model spellings silently fail on Copilot CLI**: Values like
   `Claude Opus 4.6 (anthropic)` fall back to the session default without error.
   Omission (inherit) is safer than any explicit value for cross-platform agents.

2. **check_model_pins.py comment was stale**: The comment claimed `.github/agents`
   was "handled by regeneration" but the parity validator confirms these files are
   hand-maintained. Updating the comment and adding the glob closes the gate gap.

3. **Commit-file-count hook requires batching**: Bulk mechanical changes across 28
   files must be split into <=5-file commits despite being a single logical change.
