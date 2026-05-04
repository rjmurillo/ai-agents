# Skill Sidecar Learnings: github (skill scripts)

**Last Updated**: 2026-05-03
**Sessions Analyzed**: 1 (PR #1873)

## Constraints (HIGH confidence)

- **Run `.claude/skills/github/scripts/pr/*.py` with a Python interpreter
  that has project deps available; `uv run python` is the simplest
  guaranteed path.** Bare `python3` fails with
  `ModuleNotFoundError: No module named 'yaml'` only when PyYAML is not
  on the interpreter's `sys.path`; if a system Python already has the
  project deps installed, bare `python3` works. The github_core package
  imports `yaml` at module load. Concrete failures observed in this
  session with the system `python3` (PyYAML absent) on:
  `get_pr_context.py`, `test_pr_merged.py`, `get_pr_review_threads.py`,
  `get_unresolved_review_threads.py`, `get_unaddressed_comments.py`,
  `get_pr_checks.py`, and `add_pr_review_thread_reply.py`. Default to
  `uv run python` to make the choice deterministic regardless of which
  interpreter `python3` resolves to. (Session PR #1873, 2026-05-03)

- **Raw `gh` may be blocked by `invoke_skill_first_guard.py` when a
  mapped skill script exists for the operation.** The
  `PreToolUse:Bash` guard examines the `gh` invocation, looks up the
  matching skill script in its mapping, and rejects with a redirect to
  that script. Operations without a mapped skill (for example
  `gh pr edit --body-file <path>`) are not blocked. Default behavior: prefer
  the skill script. Fall back to raw `gh` only when the guard does not
  redirect. (Session PR #1873, 2026-05-03; reinforces AGENTS.md "Never
  use raw gh when skills exist")

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
  stderr and JSON to stdout.** Streams are clean if you redirect them
  separately. The header-mixed-with-JSON failure surfaces only when you
  capture combined output via `2>&1` or `> file 2>&1`, where the stderr
  header lands on the first line and breaks `json.loads`. Two options:
  (1) write stdout-only: `script.py --pull-request N > out.json` (no
  stderr capture); (2) if you must capture combined output, strip the
  first line before `json.loads`, for example via `tail -n +2 file` or
  splitting on the first newline. Failure mode if not handled:
  `json.JSONDecodeError: Extra data: line 1 column 12 (char 11)`.
  (Session PR #1873, 2026-05-03)

- **`gh pr edit --body-file <path>` is the right path for replacing PR
  body content.** Skill scripts do not include a PR-edit wrapper; raw
  `gh pr edit` is acceptable for this specific operation since
  `invoke_skill_first_guard.py` does not redirect it (no mapped skill).
  (Session PR #1873, 2026-05-03)

## Notes for Review (LOW confidence)

- **`gh api repos/.../actions/runs/<id>/jobs` returns the failing-job
  list more directly than `gh run view --json jobs`.** The latter
  sometimes returns no output for cross-job aggregations. (Session PR
  #1873, 2026-05-03)
