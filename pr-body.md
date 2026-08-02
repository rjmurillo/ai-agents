Five CI correctness fixes from the ci-correctness campaign.

## Summary

**\#4285** `pre_pr_sequence.py` hits the taste-lint file-size ceiling but it is
a registration list of 48 gates, not logic. Added the `taste-lint: ignore
file-size` comment to exempt it. This was a blocking ratchet regression on main.

**\#4210** Six workflows invoked scripts with bare `python3`, which lacks the
venv PTH injection that makes `scripts.*` importable. Switched to
`uv run --frozen python` in all affected workflows. Added `astral-sh/setup-uv`
steps where uv was not already set up.

**\#4118** `markdownlint --fix` fires MD018 on bare issue references like
`\#2079 title` and rewrites them to `# 2079 title` (an H1 heading). Disabled
MD018 in `.markdownlint-cli2.yaml` because `\#NNNN` is a legitimate GitHub
issue reference pattern used throughout this repo's prose.

**\#4087** The skill discriminator only accepted `--changed-files`, so
pre-existing candidates were invisible. Added `--all` to scan all agents
unconditionally. Added a weekly `schedule` trigger so every agent is re-checked
without a PR.

**\#4057** The concurrent-PR stale-baseline scenario was untested. Added a
regression test that creates a real git repo, simulates branch A lowering the
baseline and merging, then proves branch B (which did not rebase) gets
`BASELINE RAISED` from `--base-ref`. Also proves a rebased branch passes.

## Changes

- `scripts/validation/pre_pr_sequence.py`: taste-lint ignore comment
- `.github/workflows/backlog-triage.yml`: uv setup + uv run
- `.github/workflows/ai-pr-quality-gate.yml`: uv setup + uv run
- `.github/workflows/update-reviewer-stats.yml`: uv setup + uv run
- `.github/workflows/pr-validation.yml`: uv run for `pr_commit_count.py`
- `.github/workflows/skillbook-validation.yml`: uv run
- `.github/workflows/validate-vendor-portability.yml`: uv setup + uv run
- `.markdownlint-cli2.yaml`: MD018 disabled
- `scripts/validation/check_agent_skill_discriminator.py`: `--all` flag
- `.github/workflows/agent-skill-discriminator-check.yml`: weekly schedule
- `tests/ci/test_count_ratchet_against_real_git.py`: concurrent-PR test

Fixes #4285
Fixes #4210
Fixes #4118
Fixes #4087
Fixes #4057
