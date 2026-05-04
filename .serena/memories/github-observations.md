# Skill Sidecar Learnings: github (skill scripts)

**Last Updated**: 2026-05-03
**Sessions Analyzed**: 1 (PR #1873)

## Constraints (HIGH confidence)

- **Always invoke `.claude/skills/github/scripts/pr/*.py` via `uv run python`,
  never bare `python3`.** Bare `python3` produces
  `ModuleNotFoundError: No module named 'yaml'` because the github_core
  package depends on PyYAML, which is in the project's `uv` venv. Concrete
  failures observed: `get_pr_context.py`, `test_pr_merged.py`,
  `get_pr_review_threads.py`, `get_unresolved_review_threads.py`,
  `get_unaddressed_comments.py`, `get_pr_checks.py`, and
  `add_pr_review_thread_reply.py` all fail this way. Fix: prepend
  `uv run` to every invocation. (Session PR #1873, 2026-05-03)

- **Raw `gh` is blocked by `invoke_skill_first_guard.py`.** Pre-tool-use
  hook redirects to the skill scripts. This is the correct pattern — do
  not work around the guard. (Session PR #1873, 2026-05-03; reinforces
  AGENTS.md "Never use raw gh when skills exist")

## Preferences (MED confidence)

- **Reply + resolve in one shot via `add_pr_review_thread_reply.py
  --resolve`.** Avoids a separate GraphQL `resolveReviewThread`
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

- **`get_unaddressed_comments.py` prefixes its JSON output with a one-line
  human-readable header (`PR #N: M comments needing action | NEW(M)`)
  before the JSON document.** Strip the first line before passing to
  `json.loads`, e.g. `tail -n +2 file.json` or split on first newline.
  Otherwise `json.JSONDecodeError: Extra data: line 1 column 12 (char
  11)`. (Session PR #1873, 2026-05-03)

- **`gh pr edit --body-file <path>` is the right path for replacing PR
  body content.** Skill scripts do not include a PR-edit wrapper; raw
  `gh pr edit` is acceptable for this specific operation since no skill
  exists to delegate to. (Session PR #1873, 2026-05-03)

## Notes for Review (LOW confidence)

- **`gh api repos/.../actions/runs/<id>/jobs` returns the failing-job
  list more directly than `gh run view --json jobs`.** The latter
  sometimes returns no output for cross-job aggregations. (Session PR
  #1873, 2026-05-03)
