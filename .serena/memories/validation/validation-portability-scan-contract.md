# Skill Markdown portability scan contract

- `check_skill_md_portability.scan_all()` returns `ref_counts`,
  `marker_counts`, `files_by_root`, and `drift_failures` from one traversal.
- `ref_counts` and `marker_counts` include plugin roots and `EXTRA_SCAN_ROOTS`.
- `files_by_root` covers plugin `skills/` roots and, as of issue #5214/PR
  #5284, every existing directory in `EXTRA_SCAN_ROOTS` (`.claude/commands`,
  `templates/agents`, `src/copilot-cli/instructions`), not only the required
  ones. `scan_all()`'s extra-dir loop populates `files_by_root[root_key]` for
  every directory `extra_scan_dirs()` returns, unconditionally:

  ```python
  for extra_dir in extra_dirs:
      ...
      root_key = extra_dir.relative_to(root).as_posix()
      ...
      paths = _iter_markdown_files(root, extra_dir)
      files_by_root[root_key] = len(paths)
  ```

  (`check_skill_md_portability.py:670-676`, current as of PR #5284's final
  revision; re-check the line numbers before quoting again, they have already
  drifted once in this PR). `REQUIRED_EXTRA_ROOTS` (currently
  just `src/copilot-cli/instructions`) governs a separate, narrower question:
  whether `main()` exits 2 via `missing_required_extra_roots()` when that
  specific directory is absent. A non-required extra root
  (`.claude/commands`, `templates/agents`) that happens to be missing is
  silently skipped by `extra_scan_dirs()` (a minimal clone may not have it)
  and simply does not appear as a key in `files_by_root`; a *required* root
  that is missing instead fails the run before scanning starts. Both kinds of
  extra root, present, contribute identically to `ref_counts`/`marker_counts`
  and to the coverage report; `REQUIRED_EXTRA_ROOTS` only changes what
  happens when the directory does not exist.
- Keep a direct regression test for extra-directory marker counts. The
  single-traversal refactor otherwise reads like a behavior change.
- `portability_common.resolve_baseline_path()` documentation should name the
  ratchets that import it. Generic `--baseline` wording drifts as validators
  add private baseline helpers.
- A `vendor-portability` marker's declared paths must match prose outside
  fenced code blocks: `marker_path_drift()` in `check_skill_md_drift.py`
  strips fenced/indented code before extracting prose paths, so a path that
  appears only inside a ```bash example reports as stale. Prefer
  directory-level declarations (`scripts/ci`, not
  `scripts/ci/ruff_count_ratchet.py`) for a rule body that legitimately names
  many files under one tree; they cover descendants via component-prefix
  matching and are immune to which specific files get added or removed later.
- A directory-prefix declaration must itself resolve on disk:
  `marker_path_drift()`'s existence check resolves every declared and prose
  path against the repo root, so declaring a bare `build/audit` when only
  `build/audit/GENERATION-AUDIT.md` exists (and only that exact file is
  exempted via `_GENERATED_ARTIFACTS`) fails. Check existence before choosing
  prefix granularity.

Refs Issue #4211, #5214 and PR #4551, #5284.
