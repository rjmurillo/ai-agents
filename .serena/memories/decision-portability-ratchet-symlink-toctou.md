# Portability ratchet: symlink containment and single-traversal scan

keywords: portability, symlink, CWE-22, TOCTOU, scan_all, refuse_symlinked_scan_root, resolve_baseline_path

## Facts recorded 2026-08-04 (session 9051, PR #4551)

`portability_common.refuse_symlinked_scan_root(root, scan_root)` raises SystemExit(2)
when the real path of scan_root escapes root. Both portability checkers call it per
scan root before walking the tree.

`resolve_baseline_path` no longer accepts `reject_outside_root`. The False branch was
dead: the one call site in `resolve_checked_baseline` always passed True. Removing it
also removed a taste violation, lowering the taste baseline by 1.

`check_skill_md_portability.scan_all()` collects plugin roots, markdown files, and
marker suppressions in a single traversal. Three prior functions are thin wrappers.
`check_skill_md_exec_portability.scan_all()` was already single-pass.

Advisory lock files (`.*.write-lock` under `scripts/validation/`) are gitignored.
They persist between runs by design; gitignore is the correct fix, not deletion.

## Tests

- `tests/validation/test_symlink_scan_root.py`: 10 tests, #4212
- `tests/validation/test_single_traversal_scan.py`: 7 tests, #4211
- `tests/validation/test_resolve_baseline_dead_branch.py`: 13 tests, #4242, #4511
