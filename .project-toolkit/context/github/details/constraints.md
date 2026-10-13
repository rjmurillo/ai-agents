## Constraints

- Job bodies live in `scripts/ci/` or `.github/scripts/`, tested in `tests/`.
- SHA pins: `scripts/validation/git_hook_policy.py staged-action-pins` locally, `scripts/validate_workflows.py` in `pr-validation.yml`.
- New concurrency groups add their `name:` to `.github/scripts/measure_workflow_coalescing.py` `DEFAULT_WORKFLOWS`, `cancel-in-progress: true` (ADR-026).
- `gh` calls in `.github/scripts/*.py` build the path as `repos/{owner}/{repo}/...`; `--repo`/`--repository` default empty and fall back to the git remote.
