# Red CI on main

## Symptom

- A required check shows a red X on the latest `main` commit.
- The Python Tests workflow opened or updated an issue titled
  "Python Tests failed on main at `<short sha>`".
  `scripts/ci/main_pytest_failure_alert.py` files it from
  [pytest.yml](../../.github/workflows/pytest.yml).
- Several unrelated PRs fail the same check at the same time.

## Confirm

Ask whether the failing check is also red on `main` before you debug a PR. The
probe walks recent `main` commits and reports the latest completed run of the
named check:

```bash
uv run --frozen python .claude/skills/github/scripts/pr/triage_red_check.py --check-name "<check name as shown on the PR>"
```

Read the `Verdict` field:

- `RED_ON_MAIN`: the failure is inherited from `main`. Cite `EvidenceUrl` and
  fix `main`, not the PR.
- `GREEN_ON_MAIN`: `main` is green. The PR introduced the failure.
- `PR_ONLY` and the other verdicts: read the `Guidance` field it prints.

For a PR, pull the failing job logs without raw `gh`:

```bash
uv run --frozen python .claude/skills/github/scripts/pr/get_pr_checks.py --pull-request <number>
uv run --frozen python .claude/skills/github/scripts/pr/get_pr_check_logs.py --pull-request <number>
```

## Recover

1. Find the first red commit. Open the failing run from `EvidenceUrl` and walk
   back through `main` history until the check was last green.
2. Decide between a flaky failure and a real one. If the same job passed on the
   same commit before, rerun only the failed jobs of that run:

   ```bash
   uv run --frozen python .claude/skills/github/scripts/pr/rerun_failed_jobs.py --run-id <run id>
   ```

   Rerun once. A second failure on the same commit is not flaky.
3. For a real failure, fix forward on a branch, or revert the commit that broke
   the check:

   ```bash
   git switch -c fix/revert-<short sha> origin/main
   git revert <sha>
   ```

   Open the PR with the `push-pr` skill. Never push to `main` directly.
4. Reproduce the check locally before you push the fix. The full local gate is:

   ```bash
   uv run python scripts/validation/pre_pr.py
   ```

   A green local run does not prove a remote check is fixed unless it runs the
   same checker with the same flags and version. Say which one you ran.
5. Close the "Python Tests failed on main" issue once the check is green on
   `main`, and cite the green run.

## Escalate

Workflows under `.github/workflows/` and gate scripts under `scripts/ci/` and
`scripts/validation/` belong to `@rjmurillo` (`.github/CODEOWNERS`). Escalate when
the fix needs a workflow change, a ruleset change, or a baseline change.

## Links

- [GOTCHAS: a branch behind main fails the count ratchets](../../.agents/governance/GOTCHAS.md)
- [Merge guards](../merge-guards.md)
