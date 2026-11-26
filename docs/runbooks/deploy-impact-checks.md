# Deploy impact checks

This repository deploys no service. A release publishes plugin files and the
`@rjmurillo/ai-agents` npm package. "Deploy impact" here means: did the release
reach users intact, and did `main` stay healthy afterward. Run these checks after
a merge to `main` that changes shipped files, and after every npm publish.

Every link below is a page in this repository's GitHub Actions or on npm. No
dashboard outside GitHub and npm exists.

## After a merge to main

| Check | Where | Healthy result |
|---|---|---|
| Required checks on the merge commit | [Python Tests](https://github.com/rjmurillo/ai-agents/actions/workflows/pytest.yml) | Latest `main` run is green |
| No open red-main issue | Issues titled "Python Tests failed on main" | None open. See [Red CI on main](red-ci-on-main.md) |
| No open scheduled-workflow failure | Issues titled "Workflow failed:" | None open. See [Workflow failure alert](workflow-failure-alert.md) |
| No open drift issue | Issues with the `drift-detected` label | None open. See [Ruleset drift alert](ruleset-drift-alert.md) and [Agent drift alert](agent-drift-alert.md) |

## After an npm publish

1. Open [Actions > npm Publish](https://github.com/rjmurillo/ai-agents/actions/workflows/publish.yml).
   The "Publish to npm" job runs its own "Verify published package" step. Confirm
   the run is green through "Attach manifest to release".
2. Confirm the registry holds the exact version:

   ```bash
   npm view @rjmurillo/ai-agents@X.Y.Z version
   ```

   An E404 means nothing reached the registry. See
   [npm publish or promotion gate failure](publish-failure.md).
3. Download the `promotion-manifest` artifact from the run. Every finding must be
   remediated or accepted. An unresolved finding means the gate should have
   blocked.
4. Watch the next scheduled runs. [Agent Metrics](https://github.com/rjmurillo/ai-agents/actions/workflows/agent-metrics.yml)
   runs weekly on Sundays at 00:00 UTC. Its "Check Metric Thresholds" job warns
   when agent coverage falls under 50 percent. A red run files a
   "Workflow failed: Agent Metrics" issue.

## What these checks cannot see

- User-side breakage after install. No telemetry returns from user machines, by
  design (see the "Data sent" statement in the [README](../../README.md#fastest-start)).
  Users report breakage through GitHub issues. Triage with
  [Bad plugin or package release](bad-release-rollback.md).
- Download counts and adoption. Read them on the package's npm page, which only
  the registry knows.

Adding client-side error reporting or usage analytics is an architecture and
privacy decision for the owner. See [Agent readiness signals](../agent-readiness.md).
