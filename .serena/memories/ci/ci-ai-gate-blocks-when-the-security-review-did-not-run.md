# Skill: Why the AI quality gate blocks on DID_NOT_RUN, and why its stated cause is hardcoded (92%)

## Statement

When `Aggregate Results` fails and nine or ten agents report the same verdict,
that is one infrastructure failure reported many times. The gate refused to
certify a PR whose security review never ran.

`github-rate-limit-payload-does-not-predict-service.md` already covers the
usual trigger, the uniform-verdict tell, and how to recover. This memory covers
the two things it does not: the summary line names a cause nothing measured,
and the block is deliberate, so repairing it removes a security requirement.

## The failure message names a cause it never measured

`scripts/ci/agent_review_check_verdict.py:57` prints:

```text
⚠️ 🔒 security review had infrastructure failure (Copilot CLI unavailable)
```

`Copilot CLI unavailable` is a literal baked into the f-string. Nothing probed
the CLI. The same claim is hardcoded in three more places:
`generate_quality_report.py:162`, `check_spec_failures.py:94`, and a comment at
`.github/actions/agent-review/action.yml:107`. Every infrastructure failure
prints it, whatever actually broke.

On the measured incident the CLI was fine, and the log says so 10 lines
earlier:

```text
Installing GitHub Copilot CLI@1.0.63...
GitHub Copilot CLI 1.0.63.
##[error]Failed to fetch PR diff for #4596 from rjmurillo/ai-agents: could not
find pull request diff: HTTP 403: API rate limit exceeded for user ID 6811113
```

The CLI installed and reported its version. The job died fetching the PR diff.
Chasing CLI availability means debugging a component that never failed.

Read the first `##[error]` in a failing agent job. The trailing summary is a
template, not a diagnosis.

## Why the per-agent job says "Not blocking PR" while the PR is blocked

Two different decisions. Reading the first as final is the trap.

`agent_review_check_verdict.py:44` derives an infra flag when both the verdict
and the findings are empty. Line 55 prints "Not blocking PR." and line 60
returns 0. That is only the per-agent step declining to fail itself. The
verdict still travels to the aggregate, which decides the gate.

`.github/scripts/aggregate_quality_verdicts.py` then splits:

| Situation | Branch | Final verdict |
| --- | --- | --- |
| All failures infra, security among them | lines 106 to 108 | `DID_NOT_RUN` |
| All failures infra, security not among them | lines 109 to 111 | `WARN` |
| Any real code-quality failure | neither | the merged verdict |

`scripts/quality_gate/check_critical_failures.py:55` blocks on `DID_NOT_RUN`:

```python
BLOCKING_VERDICTS = frozenset(FAIL_VERDICTS | {"UNKNOWN", "DID_NOT_RUN"})
```

The `WARN` escape is narrower than it looks. `get_category` returns
`INFRASTRUCTURE` only for verdicts in `FAIL_VERDICTS` (`CRITICAL_FAIL`, `FAIL`,
`NEEDS_REVIEW`, `NON_COMPLIANT`, `REJECTED`). `DID_NOT_RUN` and `UNKNOWN` are
not members, so a non-security agent reporting `DID_NOT_RUN` is categorized
`N/A`, merges to `UNKNOWN` (`scripts/ai_review_common/verdict.py:122`), misses
the line 109 guard, and still blocks. The downgrade only rescues infra failures
carrying a `FAIL_VERDICTS` token such as `NEEDS_REVIEW`.

## Chesterton's fence: three edits that look like fixes

The asymmetry reads like an oversight. It is not.
`check_critical_failures.py:24` records the reason: issue #2818 added
`DID_NOT_RUN` so an infrastructure failure that skips the review cannot pass.
Issue #2821 chose this over the alternative, and
`aggregate_quality_verdicts.py:120` prints the rationale at runtime:

```text
::warning title=Security review did not run::The AI security review hit an
infrastructure failure and did not evaluate this PR. The gate verdict does not
certify a security review; re-run the gate or review security manually before
merge (issue #2821).
```

The remedy is in the warning itself. Two edits turn the gate green while
removing the requirement that the security review happen, and the resulting
failure is silent and permanent:

- Removing `DID_NOT_RUN` from `BLOCKING_VERDICTS`.
- Widening the line 109 `WARN` downgrade to cover security.

A third edit is inert rather than dangerous, and worth knowing so you do not
spend time on it. Changing `_BLOCKING_VERDICTS` at
`agent_review_check_verdict.py:28` changes nothing.
`scripts/ci/agent_review_save_results.py:56` has already defaulted the empty
verdict to `NEEDS_REVIEW`, set the infra flag, and written the artifact, and
`action.yml` uploads it at line 157 before the verdict check runs at line 187.
The aggregate reads the artifact, not the check step.

## Confirming the classification

The aggregate job logs a per-agent infra flag:

```bash
gh api repos/OWNER/REPO/actions/jobs/<aggregate-job-id>/logs \
  --allow-escape-sequences | sed 's/\x1b\[[0-9;]*[a-zA-Z]//g' \
  | grep -E "\(infra: (true|false)\)|FINAL_VERDICT"
```

`(infra: true)` on every failing agent plus `FINAL_VERDICT: DID_NOT_RUN` proves
the aggregate classified these as infrastructure. It does not say what failed.

The repo also labels the PR `infrastructure-failure` via
`scripts/quality_gate/check_infrastructure_failures.py`. That script only adds
the label and has no removal path, so the label may be left over from an
earlier run. Supporting evidence, never proof about this run.

For recovery, including why `gh run rerun --failed` cannot work on this
workflow, see `github-rate-limit-payload-does-not-predict-service.md`.

## Evidence

Measured 2026-08-05 on two PRs whose diffs were memory files only.

| PR | Run | Agents infra:true | QA | Final verdict |
| --- | --- | --- | --- | --- |
| #4596 | 30969590662 | 9 of 10 | `PASS` (infra:false) | `DID_NOT_RUN` |
| #4593 | 30966540941 | 9 of 10 | `PASS` (infra:false) | `DID_NOT_RUN` |

Security job 92190890958 (#4596) carries the `HTTP 403` quoted above. The
#4593 security job 92181726500 failed identically.

All ten agent jobs reported `success` at the job level while nine produced no
verdict at all. Job conclusion is not evidence a review ran.

QA passed in both runs because it ran later, after PR-diff retrieval recovered.
That is an inference from job ordering, not a measured claim. A single passing
agent among nine infra failures is a scheduling artifact, not a partial review.

Both runs were re-run with no change to either diff and reached `attempt=2
conclusion=success` with 0 failing checks. Treat that as consistent with the
diagnosis, not as proof of it: the reviewers are not deterministic, so a clean
rerun cannot by itself rule out a real finding. The `HTTP 403` in the logs is
what proves these were infrastructure failures.

## Anti-Pattern

Reading `❌ AI Quality Gate FAILED / Agents with blocking verdicts:` as nine
findings and starting to address them. The entries carry no text because no
review produced any.

Equally wrong: taking `(Copilot CLI unavailable)` at face value and debugging
the CLI.

Worst: concluding "all failures are INFRASTRUCTURE, so the gate is buggy" and
editing the gate. Check whether security is in the infra set first. If it is,
the block is the design.

## Related

- `github-rate-limit-payload-does-not-predict-service.md` (the usual trigger, the two refusal modes, and recovery)
- `ci-infrastructure-003-job-status-verdict-distinction.md` (job status is not verdict; this is that distinction's sharpest instance)
- `ci-a-red-check-on-your-pr-may-be-inherited-from-main.md` (when `gh run rerun` cannot help)
- `ci-infrastructure-001-fail-fast-infrastructure-failures.md`
