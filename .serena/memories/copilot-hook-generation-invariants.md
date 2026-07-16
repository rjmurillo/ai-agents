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

## Cross-platform tests

Windows publish simulations must initialize the hook-generation transaction
using the host platform's locking implementation, then scope `_IS_WINDOWS` and
the replacement operation only around publish calls. Setting `_IS_WINDOWS`
before transaction initialization imports Windows-only locking modules on
Linux and invalidates the simulation.

Repository-root discovery for observation sync is fail closed. A timeout or
missing Git executable returns no root instead of treating the current working
directory as verified.

## Evidence

PR 3076 session 3045 covered the cleanup contract with positive, protected,
and filesystem-error cases. The focused suites passed 53 tests, and the full
suite passed 14,284 tests with 20 skips and 45 expected failures.

## Related

- [copilot-agent-frontmatter-ci-enforcement](copilot-agent-frontmatter-ci-enforcement.md)
- [copilot-agent-frontmatter-ci-review-fixes](copilot-agent-frontmatter-ci-review-fixes.md)
- [copilot-disable-all-hooks-windows](copilot-disable-all-hooks-windows.md)
- [copilot-hooks-observations](copilot-hooks-observations.md)
