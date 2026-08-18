# Retrospective: Issue #4938 Model Pin Removal

**Date**: 2026-08-14
**Issue**: #4938
**Branch**: fix/4938-remove-copilot-model-pins

## Failure Mode Classification

**Class 10: Silent Defaults and Guard-Clause Suppression**

The `.github/agents/` directory carried explicit `model:` frontmatter values
(e.g. `Claude Opus 4.6 (anthropic)`, `sonnet`) that silently fell back to the
session default on Copilot CLI without error. The governance gate
(`check_model_pins.py`) did not scan this directory, so drift accumulated
undetected across 27 files.

## Evidence

- Issue: https://github.com/rjmurillo/ai-agents/issues/4938
- Offending files: all 31 `.github/agents/*.md` prior to this fix
- Gate gap: `check_model_pins.py` `_UNIT_GLOBS` did not include `.github/agents/*.md`
- CI run confirming fix: PR #5040

## Remediation

| Action | Owner | Status |
|--------|-------|--------|
| Remove all `model:` lines from `.github/agents/` | PR #5040 | Done |
| Add `.github/agents/*.md` to `_UNIT_GLOBS` | PR #5040 | Done |
| Add regression tests (positive, negative, edge) | PR #5040 | Done |
| Remove orphaned `model-rationale` from code-reviewer | PR #5040 | Done |

## Learnings

1. **Display-name model spellings silently fail on Copilot CLI**: Values like
   `Claude Opus 4.6 (anthropic)` fall back to the session default without error.
   Omission (inherit) is safer than any explicit value for cross-platform agents.

2. **check_model_pins.py comment was stale**: The comment claimed `.github/agents`
   was "handled by regeneration" but the parity validator confirms these files are
   hand-maintained. Updating the comment and adding the glob closes the gate gap.

3. **Commit-file-count hook requires batching**: Bulk mechanical changes across 28+
   files must be split into <=5-file commits despite being a single logical change.
