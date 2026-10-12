## Architecture

- Lib (B5): `lib_mirror.py` renders `scripts/{hook_utilities,github_core,ai_review_common}`, `hook_utilities/bootstrap.py`, and `validation/validate_review_marker.py` (only canonical copy) into `src/{claude,copilot-cli}/lib/` and each tree's `skills/review/scripts/`; binplace copies the claude side onto `.claude/lib/` and the review sidecar (`lib-*`, `skills-sidecar` rows). `--check` exits 2 on drift. `.claude/lib/` top-level modules have no `scripts/` source; hand-maintained (`.claude/AGENTS.md`).
