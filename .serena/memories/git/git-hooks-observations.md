# Skill Sidecar Learnings: Git Hooks

**Last Updated**: 2026-03-01
**Sessions Analyzed**: 2 (Sessions 1190, PR-1363)

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

- Pre-commit hook `set -e` on line 21 causes silent exit when subcommands return non-zero (PR-1363, 2026-03-01)
  - Evidence: Line 1782 `SCOPE_OUTPUT=$("${PYTHON_CMD[@]}" "$SCOPE_DETECT_SCRIPT" 2>&1)` exits hook when scope detector returns 1. The proper handler at line 1784 never executes.
  - Impact: Commits fail silently. All checks appear to pass, but git commit returns exit code 1 with no error message.
  - Root Cause: Variable assignment with command substitution under `set -e` exits on non-zero without reaching `SCOPE_EXIT=$?` on next line.
  - Debugging: Use `bash -x .githooks/pre-commit` or `GIT_TRACE=2 git commit` to trace execution.

- Generator output must match .gitattributes eol setting or hook regeneration creates infinite loop (PR-1363, 2026-03-01)
  - Evidence: `build/generate_agents.py` line 228 converted to CRLF. `.gitattributes` line 59 enforces `eol=lf`. Hook regenerated CRLF, git normalized to LF on stage, hook detected change, regenerated CRLF again. Commit never completed.
  - Fix: Changed generator to output LF, matching .gitattributes. Historical context: CRLF was added before PR #902 (which introduced eol=lf).

## Preferences (MED confidence)

- BREAKING CHANGE commits use exclamation mark in conventional commit format (Session 1190, 2026-02-08)
  - Evidence: `feat(hooks)!:` format used for breaking change removing bypass mechanisms
  - Commit message included "BREAKING CHANGE:" footer explaining removal of SKIP_PREPUSH and SKIP_TESTS

- SKIP_SCOPE_CHECK=1 is the sanctioned bypass for bulk changes exceeding 50-file limit (PR-1363, 2026-03-01)
  - Evidence: Model version update touched 55 files (46 agents + 2 configs + 1 test + 1 generator). Scope detector blocked. Bypass was appropriate and documented in hook output.
  - Pattern: Regeneration of all agents from templates is a common scenario that legitimately exceeds the limit.

## Edge Cases (MED confidence)

- Python import test can hang indefinitely on system errors - discovered via timeout (Session 1190, 2026-02-08)
  - Evidence: `timeout 5 git commit` revealed Python hanging instead of failing fast when given system error
  - Workaround: Check if python3 command exists, skip import validation if prone to hanging

- Pre-push hook `set_python_cmd` finds system python3 (no pytest), not venv python (PR-1363, 2026-03-01)
  - Evidence: Push failed with "No module named pytest". System python3 at /usr/bin/python3 lacks test dependencies. Venv at .venv/bin/python has them.
  - Workaround: `PATH="$(pwd)/.venv/bin:$PATH" git push` or `PATH="$(pwd)/.venv/bin:/usr/bin:/bin:$PATH" git push`
  - Note: Same issue affects sqlite3 CLI detection in test_claude_mem_scripts.py

- GIT_TRACE=2 reveals full hook execution including where `set -e` exits (PR-1363, 2026-03-01)
  - Evidence: Standard commit output showed all checks passing. `GIT_TRACE=2` showed execution stopped after scope detector. `bash -x .githooks/pre-commit` confirmed HOOK_EXIT=1.
  - Technique: When commits fail silently, use `bash -x .githooks/pre-commit` first (faster), then `GIT_TRACE=2 git commit` for full git-level trace.

## Related Memories

- `.agents/retrospective/2026-02-08-session-1187-skip-prepush-abuse.md` - Full retrospective analysis
- `rootcause-escape-hatch-misuse.md` - Root cause pattern RootCause-Escape-Hatch-Misuse-001
- `quality-gates-bypass-enforcement.md` - Enforcement recommendations
- `process-bypass-pattern-generalization.md` - Pattern generalization analysis
