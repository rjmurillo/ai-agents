## Entry points

- `workflows/pr-validation.yml`, job `Validate PR`: required check. PR body shape, commit count, workflow YAML, ADR-006 scan, rule `paths:` keys, bare-`python3` doc entrypoints, memory-index token ratchet.
- `.github/scripts/*.py` (18) and repo-root `scripts/ci/` (105) carry most job logic; others scatter, mostly `scripts/validation/`. Grep it. There is no `.github/scripts/ci/`.
