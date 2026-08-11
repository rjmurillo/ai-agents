# Descendant symlink containment in portability validators

Issue #4759 closed the gap left after PR #4551. Scan-root checks were not
enough because descendant files or directories could still resolve outside
the repository.

## Pattern

- Use `resolve_path_within_root(root_resolved, candidate)` from
  `scripts/validation/portability_common.py`.
- `tracked_coverage_by_root()` treats tracked paths whose resolved target
  leaves the repository as missing.
- `check_skill_md_portability.py` rejects external descendant directories and
  files before traversal or read.
- `check_skill_md_exec_portability.py` rejects external descendant skill
  directories and files before probing or reading their content.

## Regression coverage

`tests/validation/test_portability_scan_coverage_refusal.py` covers:

- file and directory symlink escapes under both shipped skill roots
- escaped `scripts/` directory symlinks under both roots
- empty or broken external targets that would otherwise return success
- tracked non-scan symlink targets escaping during `--update-baseline`
