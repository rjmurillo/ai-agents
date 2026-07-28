# Retrospective: PR #3561 pytest temp root isolation

## Learnings Captured

### Finding 1: Deferred availability checks must produce clean errors
Removing an early `shutil.which` guard exposes uncaught `FileNotFoundError`
at the subprocess call site. Deferred checks are correct for testability,
but the deferred path must still emit a clean diagnostic and correct exit code.

### Finding 2: Custom fixture overrides must reproduce framework behaviors
Overriding `tmp_path` to relocate directories is valid, but the replacement
must reproduce retention cleanup. Pytest's `tmp_path_retention_policy=failed`
deletes passing-test directories; omitting this causes test artifacts to accumulate.

### Finding 3: CI must exercise the failure configuration
The original 28-test failure only manifests when `TMPDIR`/`--basetemp` points
inside the worktree. Standard CI never exercises this configuration. A dedicated
test leg or focused assertion is needed to prevent regression.

## Session Context
- PR: #3561
- Issue: #3511
- Branch: wt/t_f1b2e3a5
- Findings addressed: 2 of 3 (Finding 3 filed as separate issue)
