# Skill Markdown portability scan contract

- `check_skill_md_portability.scan_all()` returns `ref_counts`,
  `marker_counts`, `files_by_root`, and `drift_failures` from one traversal.
- `ref_counts` and `marker_counts` include plugin roots and `EXTRA_SCAN_ROOTS`.
- `files_by_root` covers plugin `skills/` roots and, as of issue #5214/PR
  #5284, any root listed in `REQUIRED_EXTRA_ROOTS` (currently
  `src/copilot-cli/instructions`). A required extra root's coverage count is
  populated in `scan_all()`'s extra-dir loop and `main()` exits 2 via
  `missing_required_extra_roots()` when the directory is absent, so it can no
  longer silently report zero files scanned. An extra root that is NOT in
  `REQUIRED_EXTRA_ROOTS` still contributes to `ref_counts`/`marker_counts` but
  is excluded from the coverage gate, same as before.
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
