# Operational runbooks

These runbooks cover the incidents that happen in this repository. The project
ships plugins and an npm package. It runs no hosted service, so every incident
here is a repository operation: a red check, a failed publish, drift between
recorded and live state, a bad release, a leaked secret, or a blocked local hook.

Each runbook lists the symptom, how to confirm it, the commands to run, how to
recover, and who owns the fix. Run every command from the repository root after
the one-command setup in [CONTRIBUTING.md](../../CONTRIBUTING.md#setup-steps).

## Runbooks

| Runbook | Use it when |
|---|---|
| [Red CI on main](red-ci-on-main.md) | A required check fails on `main`, or a "Python Tests failed on main" issue opens |
| [npm publish or promotion gate failure](publish-failure.md) | The npm Publish workflow fails or the promotion gate blocks |
| [Ruleset drift alert](ruleset-drift-alert.md) | A "Ruleset Parameter Drift Detected" or "Ruleset Required Context Drift Detected" issue opens |
| [Agent drift alert](agent-drift-alert.md) | An "Agent Drift Detected" issue with the `drift-detected` label opens |
| [Bad plugin or package release](bad-release-rollback.md) | Users report that a plugin update or an npm version broke them |
| [Leaked secret](secret-leak.md) | A token, key, or password reached a commit, PR, issue, or log |
| [Local hook or pre-push failure](local-hook-failure.md) | A Lefthook pre-commit or pre-push job blocks your commit or push |

## Owner

`.github/CODEOWNERS` names `@rjmurillo` as the owner of the workflows, the gate
scripts under `scripts/ci/` and `scripts/validation/`, `build/scripts/`,
`templates/agents/`, `lefthook.yml`, and the promotion gate files. CODEOWNERS has
no catch-all rule, so other paths, such as `RELEASING.md`, the npm package, and
the marketplace manifests, get no automatic owner review. `@rjmurillo` is the
only maintainer, so escalate to that account when a runbook says to. Report a vulnerability through a private advisory,
as [SECURITY.md](../../SECURITY.md) describes.

## Conventions

- Use the GitHub skill scripts under `.claude/skills/github/scripts/` for GitHub
  reads and writes. The repository rules forbid raw `gh` calls from agents.
- Do not skip hooks with `--no-verify` and do not force-push. Fix the cause.
- Change state through a pull request. A runbook that edits a baseline, a
  workflow, or a release file still needs a reviewed PR.
