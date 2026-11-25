# ADR Debate Log: re-anchor post-merge citations in ADR-102 and ADR-115

## Summary

- **Rounds**: 1 of 10
- **Outcome**: Consensus
- **Final Status**: unchanged (the edit changes no ADR status or decision)
- **Scope**: citation-only edits in ADR-102 and ADR-115 after merging `origin/main` through `ce18cc4d7` on branch `fix/agent-readiness-signals`.
- **Panel**: reduced panel, architect and critic. The edit changes citations only. No enforcement logic changes.

## Round 1 Summary

### Scope and Diff Verified

1. `.project-toolkit/architecture/ADR-115-native-plugin-support-per-host.md:122`: replaced untracked relative path `skillforge/references/script-design-rules.md:232` with the canonical tracked repository path `src/claude/skills/skillforge/references/script-design-rules.md`. Enforcement remains pinned by line number and SHA-256 in `FORCE_ALLOWED_FINDINGS` (`tests/e2e/hermes_runtime.py:118-127`).
2. `.project-toolkit/architecture/ADR-102-session-qa-binding-field-precedence.md:221-222`: wrapped line 221 after `binding.` onto line 222 so the former `ci-scripts` rule reference no longer collides with the `git_hook_policy.py:2789` anchor check in `citation_reverse_pass.py`. `scripts/validation/git_hook_policy.py:2789` remains `flags = ["--creation-mode"] if session in new_logs else ["--pre-commit", "--existing-log"]`.

### Key Issues Addressed

- `check_citation_freshness.py` flagged `ADR-115:122` because `skillforge/references/script-design-rules.md` lacked the `src/claude/skills/` prefix tracked at `HEAD`.
- `citation_reverse_pass.py` flagged `ADR-102:221` because `ci-scripts` sat on the same line as `git_hook_policy.py:2789` after PR `#7541` rewrote `.claude/rules/ci-scripts.md` to "the former `ci-scripts` rule".

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept. Verified both target files (`src/claude/skills/skillforge/references/script-design-rules.md:232`, `scripts/validation/git_hook_policy.py:2789`, `tests/e2e/hermes_runtime.py:118-127`, `.claude/skills/ai-agents-validation-and-qa/references/rule-ci-scripts.md:61-72`), no status or decision changes. |
| critic | Accept. Verified dropping `:232` from ADR-115 prose loses no enforcement (`FORCE_ALLOWED_FINDINGS` remains authoritative), wrapping ADR-102:221 preserves CommonMark paragraph meaning without hiding drift, and ASCII punctuation is clean. |
