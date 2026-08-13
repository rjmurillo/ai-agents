# Skill Markdown portability scan contract

- `check_skill_md_portability.scan_all()` returns `ref_counts`,
  `marker_counts`, `files_by_root`, and `drift_failures` from one traversal.
- `ref_counts` and `marker_counts` include plugin roots and `EXTRA_SCAN_ROOTS`.
- `files_by_root` covers only plugin `skills/` roots. Extra scan directories
  never affect the coverage gate.
- Keep a direct regression test for extra-directory marker counts. The
  single-traversal refactor otherwise reads like a behavior change.
- `portability_common.resolve_baseline_path()` documentation should name the
  ratchets that import it. Generic `--baseline` wording drifts as validators
  add private baseline helpers.

Refs Issue #4211 and PR #4551.
