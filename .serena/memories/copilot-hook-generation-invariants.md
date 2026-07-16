# Copilot hook generation invariants

## Generated shim cleanup

The Copilot dispatcher generator owns stale matcher-shim removal. A stale file
is eligible for deletion only when all of these conditions hold:

- The file is a Python file in a generated event directory.
- `generate_hooks_body.is_shimmed` identifies generated shim content.
- The authoritative event manifest does not register the file.
- `regen_guard.detect_reason_strict` finds no inline or sidecar `NO-REGEN`
  protection.

Do not infer generated ownership from a filename containing `__`. Event
directories can contain support modules with that naming shape. Cleanup must
also propagate scan, read, and unlink failures; silently accepting a partial
cleanup can ship stale hook behavior. Protected stale shims remain in place and
the generator emits a notice naming the protection reason.

When dispatcher artifacts are staged off-tree, stale candidates must be
discovered in the published event directory rather than the empty staging
directory. Their deletion belongs to the same `HookGenerationTransaction` as
script, dispatcher, and configuration publication so a later failure restores
the stale shim. On Windows, a fresh deletion moves the original file object
into the journal to preserve metadata; a target already backed up in the same
transaction is unlinked without replacing the immutable first backup.

## Path safety

Event names must be one path component before any staging directory is created.
Stale cleanup uses `lstat()` to reject symlinked event directories and files,
then resolves each candidate under the resolved hooks root before adding it to
the deletion transaction. Windows compares active shim names with `casefold()`
so a case-only rename cannot classify the active file as stale.

`HookGenerationTransaction.delete_many` deduplicates targets and treats missing
or repeated deletions as no-ops. If a Windows move creates the journal backup
then raises, the transaction records the mutation so rollback restores the
original file object.

## Cross-platform tests

Windows publish simulations must initialize the hook-generation transaction
using the host platform's locking implementation, then scope `_IS_WINDOWS` and
the replacement operation only around publish calls. Setting `_IS_WINDOWS`
before transaction initialization imports Windows-only locking modules on
Linux and invalidates the simulation.

Repository-root discovery for observation sync is fail closed. A timeout or
missing Git executable returns no root instead of treating the current working
directory as verified.

## Protocol encoding

Session-start context output is a UTF-8 protocol. The canonical context loader
reconfigures text streams to UTF-8 and explicitly encodes the binary fallback.
Edit `.claude/hooks/SessionStart/invoke_context_loader.py`, then regenerate its
Copilot CLI mirror rather than editing the generated file.

## Evidence

PR 3076 sessions 3045 and 3046 covered positive, protected, filesystem-error,
transaction rollback, symlink, path traversal, case-only Windows naming, and
partial Windows move cases. Commit `4c83b4d7` passed all 817 build-script tests
with 1 platform skip, focused Ruff, normal and Windows mypy, generated drift
checks, a real POSIX symlink reproduction, and independent correctness and
security reviews.

## Related

- [copilot-agent-frontmatter-ci-enforcement](copilot-agent-frontmatter-ci-enforcement.md)
- [copilot-agent-frontmatter-ci-review-fixes](copilot-agent-frontmatter-ci-review-fixes.md)
- [copilot-disable-all-hooks-windows](copilot-disable-all-hooks-windows.md)
- [copilot-hooks-observations](copilot-hooks-observations.md)
