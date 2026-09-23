Fixed in commit 94b2a7a3 (M7-T3, rebased to current head).

Root cause: `invoke_session_log_guard.py` is registered under both `Bash(git commit*)` and the pr-creation matcher in `.claude/settings.json`, but the body only called `is_git_commit_command(command)`. The pr-creation copy of the shimmed hook fired correctly, then the body returned 0 immediately because the command did not match git commit. The session-log gate silently no-opped for half the commands it was meant to enforce.

Fix:
- Added `is_pr_create_command()` and `is_session_logged_command()` aggregate predicate to `scripts/hook_utilities/utilities.py`. Synced to `.claude/lib/`.
- Updated `invoke_session_log_guard.py` body to call `is_session_logged_command(command)`. Hook now enforces the gate for both registered matchers.

Tests:
- `TestIsPrCreateCommand` (8 cases) and `TestIsSessionLoggedCommand` (7 cases) in `test_hook_utilities.py` cover positive/negative matches, whitespace, empty/None, substring rejection.
- `TestM7T3MultiMatcherSessionLogGuard` (3 cases) in `test_session_log_guard.py` locks the behavioral fix: pr-creation with valid log passes, without log blocks (exit 2), unrelated commands no-op.

Inventory of the other 3 multi-matcher hooks confirmed: branch_context_guard, branch_protection_guard, adr_lifecycle_hook all already branch correctly on `tool_name` or use `is_git_commit_or_push_command`. No other multi-matcher body bugs.

988 tests pass. Resolving.
