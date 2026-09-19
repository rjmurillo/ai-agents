## Architecture

- Lib (B5): `lib_mirror.py` renders `scripts/{hook_utilities,github_core,ai_review_common}`, `hook_utilities/bootstrap.py`, and `validation/validate_review_marker.py` into `src/claude/lib/`, `src/copilot-cli/lib/`, and `src/claude/skills/review/scripts/`; binplace copies the claude side onto `.claude/lib/` and the review sidecar (`lib-*`, `skills-sidecar` rows). `.claude/lib/` top-level modules (`claude_hook_dispatch.py`, `paths.py`, siblings) have no `scripts/` source and stay hand-maintained there (`.claude/AGENTS.md`).
