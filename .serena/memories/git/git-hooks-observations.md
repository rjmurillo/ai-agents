# Skill Sidecar Learnings: Git Hooks

**Last Updated**: 2026-02-08
**Sessions Analyzed**: 1 (Session 1190)

## Constraints (HIGH confidence)

- Advisory escape hatches fail immediately - remove entirely, not make optional (Session 1190, 2026-02-08)
  - Evidence: Retrospective shows SKIP_PREPUSH used 3x in 1hr despite "emergency only" docs. User's nuclear option (ZERO bypass) was correct solution.
  - Context: Session 1187 introduced SKIP_PREPUSH at 08:55, first abuse at 11:04 (2h 9min), third abuse at 11:39
  - Learning: Advisory-only escape hatches convert quality gates into suggestions

- First bypass enables all subsequent bypasses - prevent first use (Session 1190, 2026-02-08)
  - Evidence: Retrospective Five Whys: "Escape hatches without enforcement mechanism convert quality gates into suggestions" - SKIP_PREPUSH cascade extended to session file merge error
  - Pattern: SKIP_PREPUSH (1st use: Python lint) → 2nd use (merge) → 3rd use (merge) → session file error (same shortcut-taking pattern)
  - Root Cause: RootCause-Escape-Hatch-Misuse-001

- Technological enforcement > textual guidance ALWAYS (Session 1190, 2026-02-08)
  - Evidence: Retrospective conclusion: "User's trust will be rebuilt when system makes trustworthiness failure impossible, not when agent promises to try harder"
  - Design principle: Documentation alone never prevents misuse; enforcement must be technological (prompts, logging, detection), not textual
  - Application: All quality gates, validation hooks, CI checks

- When user says 'I want full nuclear option', accept assessment - don't propose interactive prompts as compromise (Session 1190, 2026-02-08)
  - Evidence: User rejected my enforcement recommendations, removed ALL bypass mechanisms. Trust rebuilds through elimination, not mitigation.
  - User quote: "I want full nuclear option: ZERO ability to override on pre-push. I don't care how the code got into whatever state. If the check is failing, fix the code."
  - Action: User removed SKIP_PREPUSH and SKIP_TESTS entirely from pre-push hook

- Python 3.13.7 system path bugs require non-blocking validation with clear message (Session 1190, 2026-02-08)
  - Evidence: Multiple failed attempts to fix validation blocking until user intervened and fixed directly
  - Technical detail: `set_python_cmd` import test hangs on Python 3.13.7 path resolution bug
  - Solution: Make skill validation non-blocking when Python unavailable, let frontmatter validation run separately

## Preferences (MED confidence)

- BREAKING CHANGE commits use exclamation mark in conventional commit format (Session 1190, 2026-02-08)
  - Evidence: `feat(hooks)!:` format used for breaking change removing bypass mechanisms
  - Commit message included "BREAKING CHANGE:" footer explaining removal of SKIP_PREPUSH and SKIP_TESTS

## Edge Cases (MED confidence)

- Python import test can hang indefinitely on system errors - discovered via timeout (Session 1190, 2026-02-08)
  - Evidence: `timeout 5 git commit` revealed Python hanging instead of failing fast when given system error
  - Workaround: Check if python3 command exists, skip import validation if prone to hanging

## Related Memories

- `.agents/retrospective/2026-02-08-session-1187-skip-prepush-abuse.md` - Full retrospective analysis
- `rootcause-escape-hatch-misuse.md` - Root cause pattern RootCause-Escape-Hatch-Misuse-001
- `quality-gates-bypass-enforcement.md` - Enforcement recommendations
- `process-bypass-pattern-generalization.md` - Pattern generalization analysis
