# The AI review preflight probes COPILOT_GITHUB_TOKEN, not the runner token

## Question

Which credential does `check-agent-infrastructure` validate, and what gates the
ten AI review jobs?

## Decision

The preflight probes `COPILOT_GITHUB_TOKEN` with `gh api user`, overriding both
`GH_TOKEN` and `GITHUB_TOKEN` in the subprocess. The review jobs gate on a
single `reviews-enabled` output, never on binary presence.

## Evidence

Issue #4778, run 31283819979 job 93169277989, reported:

```text
Authentication: FAILED
Copilot CLI available via gh extension
Overall: unavailable
Agent reviews requiring Copilot CLI will be skipped.
```

All ten reviewer jobs then ran and each died with:

```text
Failed to fetch PAT user login (401): GitHub returned: Bad credentials
Failed to fetch GitHub CLI user login (403): GitHub returned: Resource not accessible by integration
```

Two independent defects:

1. PR #4648 pointed the probe's `GH_TOKEN` at the runner installation token.
   An installation token can never resolve `/user`, so `Authentication: FAILED`
   was guaranteed regardless of credential health.
2. The workflow gated on `copilot-available` (binary presence only), so the
   `unavailable` grade never reached the review jobs.

## Consequence

`scripts/ci/check_agent_infrastructure.py` grades the credential four ways,
mirroring `tests/e2e/copilot_hook_probe.py`:

| Status | Meaning | Reviews |
| --- | --- | --- |
| `valid` | GitHub accepted the credential | run |
| `rejected` | GitHub refused it; rotate the secret | skip |
| `absent` | not provisioned; create the secret | skip |
| `unverified` | rate limit or transport fault; status unknown | run |

`unverified` does not block: a GitHub blip must not become a repository-wide
review outage, and the review has its own retry path.

Outputs are `copilot-available` (binary only), `copilot-auth-status`,
`auth-valid`, `reviews-enabled` (the gate), and `overall-status`.

## Two rules this established

1. Gate with `== 'true'`, never `!= 'unavailable'`. A skipped or failed upstream
   job publishes an empty output; `!=` reads that as pass.
2. Fail-closed gating and artifact production must land together.
   `scripts/quality_gate/validate_artifact_download.py` exits 1 on a missing
   `<agent>-verdict.txt`, so a silent skip crashes aggregation before it can
   post a report. `.github/actions/agent-review/action.yml` therefore splits
   `should-run` (changes present; gates save and upload) from `infra-ready`
   (gates only the model call), and `scripts/ci/agent_review_outcome.py`
   records `DID_NOT_RUN` plus an infrastructure flag when the preflight blocks.
   Both `infra-ready` and `INFRA_READY` default to not-ready.

Fixed in PR for issue #4778. Related: #4777 (fail-open aggregate), #3275
(invalid Copilot credential), #4648 (runner-token preference).
