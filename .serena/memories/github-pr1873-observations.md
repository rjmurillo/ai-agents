# Skill Sidecar Learnings: github (skill scripts)

**Last Updated**: 2026-07-21
**Sessions Analyzed**: 1 (PR #1873)

## Constraints (HIGH confidence)

- **Run `.claude/skills/github/scripts/pr/*.py` with a Python interpreter
  that has project deps available; `uv run python` is the simplest
  guaranteed path.** The scripts import `github_core` (at
  `.claude/lib/github_core/`), which imports `yaml` at module load.
  Bare `python3` fails with `ModuleNotFoundError: No module named 'yaml'`
  when PyYAML is not on the interpreter's `sys.path`. `uv run python`
  resolves the project venv deterministically regardless of which
  interpreter `python3` resolves to. (Session PR #1873, 2026-05-03)

- **Use skill scripts when they exist.** `AGENTS.md` keeps this as a MUST-level
  rule. PR #3293 retired `invoke_skill_first_guard.py`, so current sessions no
  longer get runtime interception or redirect messages. Raw `gh` remains valid
  only where no skill script covers the operation. (Session PR #1873,
  2026-05-03; retirement 2026-07-21)

## Preferences (MED confidence)

- **Reply + resolve in one shot via `add_pr_review_thread_reply.py --resolve`.**
  Avoids a separate GraphQL `resolveReviewThread`
  mutation. For batches of N threads, write a small Python loop that
  calls the script per `(thread_id, body)` pair; this completed 19
  threads in <30 seconds in round 1 and 8 in round 4. (Session PR #1873,
  2026-05-03)

- **Use `(?ms)##\s+Changes\s*\n+(?!##)\s*[-*]` regex shape when checking
  template compliance against
  `.claude/skills/github/scripts/pr/validate_pr_description.py`.** The
  validator wants a bullet line immediately after the `## Changes`
  heading; subheadings (`###`) without preceding bullets fail the
  Changes-section gate while still passing Summary, Spec References, and
  Type-of-Change. (Session PR #1873, 2026-05-03)

## Edge Cases (MED confidence)

- **`get_unaddressed_comments.py` writes a human-readable summary to
  stderr and JSON to stdout.** Capture stdout only, e.g.
  `uv run python .claude/skills/github/scripts/pr/get_unaddressed_comments.py --pull-request 1873 > out.json`;
  a `2>&1` combined capture prepends the stderr header to the JSON
  and trips `json.JSONDecodeError: Extra data: line 1 column 12 (char 11)`.
  (Session PR #1873, 2026-05-03)

- **`gh pr edit --body-file <path>` is the right path for replacing PR
  body content.** Skill scripts do not include a PR-edit wrapper; raw
  `gh pr edit` is acceptable for this specific operation because no skill
  script covers it.
  (Session PR #1873, 2026-05-03)

## Notes for Review (LOW confidence)

- **`gh api repos/.../actions/runs/<id>/jobs` returns the failing-job
  list more directly than `gh run view --json jobs`.** The latter
  sometimes returns no output for cross-job aggregations. (Session PR
  #1873, 2026-05-03)
