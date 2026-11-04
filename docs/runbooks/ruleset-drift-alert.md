# Ruleset drift alert

Two scheduled checks compare the live branch ruleset with the state this
repository records. Each one opens an issue when they disagree.

| Workflow | Program | Issue title |
|---|---|---|
| [Check Ruleset Drift](../../.github/workflows/check-ruleset-drift.yml) | `scripts/validation/check_ruleset_params_drift.py --alert` | Ruleset Parameter Drift Detected |
| [Ruleset Required Context Drift](../../.github/workflows/ruleset-context-drift.yml) | `scripts/ci/ruleset_context_drift.py --alert` | Ruleset Required Context Drift Detected |

Each workflow file sets its own schedule.

## Symptom

- An open issue with one of the titles above and the `drift-detected` label.
- A red run of either workflow.

## Confirm

Run both checks locally. They only read the live ruleset through the GitHub API,
so they need an authenticated `gh` session:

```bash
uv run --frozen python scripts/validation/check_ruleset_params_drift.py
PYTHONPATH=. uv run --frozen python scripts/ci/ruleset_context_drift.py
```

Without `--alert` they print the drift and file nothing. Exit codes follow
ADR-035:

| Exit | Meaning |
|---|---|
| 0 | Live state matches the recorded state |
| 1 | Drift found |
| 2 | Local configuration error, such as a missing or malformed baseline |
| 3 | GitHub API or issue operation failed |
| 4 | `gh` is not authenticated |

The Actions token cannot see `bypass_actors`, so the scheduled parameter check
skips that comparison and logs it. Run the parameter check with an admin token to
compare `bypass_actors` too.

A red run with exit 3 or 4 is a tooling or token problem, not drift. Check the
run log before you touch the ruleset.

## Recover

First decide whether someone changed the ruleset on purpose.

- **The change was not intended.** Restore the ruleset in
  [Settings > Rules > Rulesets](https://github.com/rjmurillo/ai-agents/settings/rules)
  to match the recorded state. Only a repository admin can do this.
- **The change was intended.** Update the recorded state in a PR so the check
  matches the live ruleset:
  - Parameters, `enforcement`, and `bypass_actors`:
    `scripts/validation/ruleset_params_baseline.json`.
  - Required status check contexts: `REQUIRED_CONTEXTS` in
    `scripts/ci/ruleset_required_contexts.py`. The parameter check leaves that
    key to this module.

Then rerun the local check until it exits 0, run the workflow by dispatch, and
close the alert issue with a link to the green run.

## Escalate

`scripts/validation/`, `scripts/ci/`, and `.github/workflows/` belong to
`@rjmurillo` (`.github/CODEOWNERS`). A ruleset change needs an admin. Treat an
unexplained new bypass actor or a weakened rule as a security event and tell the
owner the same day.

## Links

- [Merge guards](../merge-guards.md)
