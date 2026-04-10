# Pre-Commit Quality Gates

**Last Updated**: 2026-04-10
**Sessions Analyzed**: 1

## Preferences (MED confidence)

- Run mypy locally before committing Python files to avoid push failures. The pre-push hook runs mypy and blocks on errors. (Session 2, 2026-04-10)
  - Evidence: Push failed on mypy errors for unparameterized dict types, required 2 fix iterations
  - Command: `python3 -m mypy <changed_files>`

- Use `dict[str, Any]` for JSON API responses from GraphQL/REST. Never `dict[str, object]` (breaks .get() chains). (Session 2, 2026-04-10)
  - Evidence: First fix attempt with `dict[str, object]` caused `"object" has no attribute "get"` mypy error

## Edge Cases (MED confidence)

- After push rejection ("remote contains work you do not have locally"), run `git pull --rebase` before retrying push. This happens when PR creation adds commits to the remote. (Session 2, 2026-04-10)
  - Evidence: Push rejected after new_pr.py added a merge commit on the remote branch