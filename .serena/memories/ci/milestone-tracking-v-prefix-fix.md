# Milestone tracking: v-prefix semver fix (issue #3945, 2026-07-30)

The milestone-tracking workflow (`.github/workflows/milestone-tracking.yml`) was a silent no-op from milestone `0.3.0` close (2026-02) to 2026-07-30: `_SEMVER_PATTERN` in `set_item_milestone.py` matched only bare `X.Y.Z` titles while every milestone created since is v-prefixed (`v0.3.1`, `v0.4.0`, ...). `--missing-milestone-ok` made every run exit green.

Fix (branch `fix/milestone-semver-v-prefix`): pattern now `^v?\d+\.\d+\.\d+$`, `_parse_semver_tuple` strips leading `v` via `removeprefix`. Five copies patched: `.github/scripts/set_item_milestone.py`, `.claude/skills/github/scripts/milestone/{set_item_milestone,get_latest_semantic_milestone}.py`, and both `src/copilot-cli` mirrors. DRY consolidation tracked in #3947.

Operational facts:
- Milestone titles are now all v-prefixed (0.2.0/0.3.0 renamed to v0.2.0/v0.3.0 on 2026-07-30).
- Historical release milestones v0.4.0 (295 issues), v0.5.0 (66), v0.6.0 (350) were backfilled by close-date window from boundary commits and closed with due dates = release dates.
- Auto-assign targets the LATEST OPEN semver milestone. Non-semver titles like `v0.6.x close-out` are deliberately invisible to it. No open semver milestone = silent no-op (by design via `--missing-milestone-ok`); create the next release milestone to resume auto-assign.
- session-init validation UX issue filed as #3946.
