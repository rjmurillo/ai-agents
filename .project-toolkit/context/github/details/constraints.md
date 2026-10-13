## Constraints

- Job bodies live in `scripts/ci/` or `.github/scripts/`, tested in `tests/`.
- SHA pins: `scripts/validation/git_hook_policy.py staged-action-pins` locally, `scripts/validate_workflows.py` in `pr-validation.yml`.
- A workflow adding a concurrency group adds its top-level `name:` (run name, not file stem) to `.github/scripts/measure_workflow_coalescing.py` `DEFAULT_WORKFLOWS`, and sets `cancel-in-progress: true` unless an ADR says otherwise (ADR-026/114).
- `gh` calls in `.github/scripts/*.py` build the path as `repos/{owner}/{repo}/...`; `--repo`/`--repository` default empty and fall back to the git remote.
