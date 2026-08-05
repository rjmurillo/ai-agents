# Skill: Why the AI quality gate blocks on DID_NOT_RUN, and why its stated cause is hardcoded (92%)

## Statement

When `Aggregate Results` fails and nine or ten agents report the same verdict,
that is usually one infrastructure failure reported many times. In the measured
incidents the gate refused to certify a PR whose security review never ran.
That refusal is deliberate, but not universal: one token combination passes
such a PR silently, which is issue #4654.

`github-rate-limit-payload-does-not-predict-service.md` already covers the
usual trigger, the uniform-verdict tell, and recovery. This memory covers what
it does not: the summary line names a cause nothing measured, the block is
deliberate so repairing it removes a security requirement, and the blocking
behavior depends on which verdict token the failing agent wrote.

## The failure message names a cause it never measured

`scripts/ci/agent_review_check_verdict.py:57` prints:

```text
⚠️ 🔒 security review had infrastructure failure (Copilot CLI unavailable)
```

`Copilot CLI unavailable` is a literal baked into the f-string. It is printed
because the code path is an infrastructure failure, not because anything
diagnosed the CLI. The same claim is hardcoded in `generate_quality_report.py`,
`check_spec_failures.py`, and a comment in `agent-review/action.yml`. It is
emitted on the fail-verdict infrastructure paths whatever actually broke.

The CLI is in fact probed, just not here and not as input to this message.
`scripts/ci/install_copilot_cli.py:64` runs `copilot --version`, and
`.github/actions/ai-review/action.yml:167` can run `diagnose_copilot_cli.py`.
Neither result reaches the string above.

On the measured incident the CLI was fine, and the log says so 10 lines
earlier:

```text
Installing GitHub Copilot CLI@1.0.63...
GitHub Copilot CLI 1.0.63.
##[error]Failed to fetch PR diff for #4596 from rjmurillo/ai-agents: could not
find pull request diff: HTTP 403: API rate limit exceeded for user ID 6811113
```

The CLI installed and reported its version. The review action then failed
fetching the PR diff. The enclosing agent job did not die: it saved results and
concluded `success`. Chasing CLI availability debugs a component that never
failed. Read the first `##[error]` in a failing agent job; the trailing summary
is a template, not a diagnosis.

## Why the per-agent job says "Not blocking PR" while the PR is blocked

Two different decisions. Reading the first as final is the trap.

`agent_review_check_verdict.py:44` derives an infra flag when both the verdict
and the findings are empty. Line 55 prints "Not blocking PR." and line 60
returns 0. That is only the per-agent step declining to fail itself. The
verdict still travels to the aggregate, which decides the gate.

`.github/scripts/aggregate_quality_verdicts.py` has three outcomes. Lines 106
to 108 force `DID_NOT_RUN` when all failures are infrastructure and security is
among them. Lines 109 to 111 downgrade to `WARN` when all failures are
infrastructure and security is not. Any real code-quality failure skips both
and keeps the merged verdict.

`scripts/quality_gate/check_critical_failures.py:55` blocks on `DID_NOT_RUN`:

```python
BLOCKING_VERDICTS = frozenset(FAIL_VERDICTS | {"UNKNOWN", "DID_NOT_RUN"})
```

## The token decides the branch, and one combination blocks nothing

An infrastructure failure does not produce one verdict token, and which token
you get decides which branch runs. Getting these backwards hides a combination
where nothing blocks at all.

`get_category` returns `INFRASTRUCTURE` only when the verdict is in
`FAIL_VERDICTS` (`CRITICAL_FAIL`, `FAIL`, `NEEDS_REVIEW`, `NON_COMPLIANT`,
`REJECTED`). `DID_NOT_RUN` and `UNKNOWN` are not members, so they categorize
`N/A`. Two decisions read that category: the line 106 branch forcing
`DID_NOT_RUN`, and the line 117 `security_review_ran` flag that prints the
warning. `N/A` fools both.

| security | other agent | security category | final | blocks | warning |
| --- | --- | --- | --- | --- | --- |
| `NEEDS_REVIEW` + infra | `PASS` | `INFRASTRUCTURE` | `DID_NOT_RUN` | yes | yes |
| `DID_NOT_RUN` + infra | `PASS` | `N/A` | `UNKNOWN` | yes | no |
| `DID_NOT_RUN` + infra | `NEEDS_REVIEW` + infra | `N/A` | `WARN` | **no** | **no** |

Row 1 is the designed path and the only one the measured incidents exercised.
Row 2 still blocks, but through `UNKNOWN` being in `BLOCKING_VERDICTS` rather
than any security rule, and prints no warning. Row 3 is a fail-open: security
did not run, the gate passes, and the warning meant to make that visible is
suppressed. Filed as issue #4654.

Do not carry away "an infra failure always blocks." Blocking depends on which
token the failing agent wrote, and the security-specific logic keys off a
category only some failure tokens ever receive.

The tokens come from different writers. `NEEDS_REVIEW` is the empty-verdict
default at `agent_review_save_results.py:56`. `DID_NOT_RUN` is selected at
`check_ai_review_infra_gate.py:69` and written at line 119. Two more routes sit
outside this pair: `invoke_copilot_cli.py:216` emits `CRITICAL_FAIL` after
retry exhaustion, and `validate_artifact_download.py:83` returns 1 on a missing
artifact, blocking before the aggregate runs.

## Chesterton's fence: three edits that look like fixes

The asymmetry reads like an oversight. It is not.
`check_critical_failures.py:24` records the reason: issue #1934 added `UNKNOWN`
so a crashed or unparseable skill forces attention, and issue #2818 added
`DID_NOT_RUN` so an infrastructure failure that skips the review cannot pass.
Commit `426c1aa28` (issue #2846) is what made the behavior fail closed across
the gates and hooks. Issue #2821 is narrower than it looks: commit `3c0b76429`
states merge semantics were left unchanged, and its contribution is the
runtime annotation at `aggregate_quality_verdicts.py:120`, a
`::warning title=Security review did not run::` telling the reader the gate
verdict does not certify a security review.

The remedy is in that warning. Two edits turn the gate green while removing the
requirement that the security review happen, and the resulting failure is
silent and permanent:

- Removing `DID_NOT_RUN` from `BLOCKING_VERDICTS`.
- Widening the line 109 `WARN` downgrade to cover security.

A third edit is inert rather than dangerous. Changing `_BLOCKING_VERDICTS` at
`agent_review_check_verdict.py:28` does not change the final gate outcome here.
`agent_review_save_results.py` already defaulted the empty verdict at line 56,
set the infra flag, and wrote the artifacts at lines 72 to 75, and `action.yml`
uploads them at line 157 before the verdict check runs at line 187. The
aggregate reads those artifacts. That set still governs whether the agent step
fails on a real blocking verdict with no infra flag, so it is not dead code.

## Confirming the classification

The aggregate job logs a per-agent verdict and infra flag:

```bash
gh api repos/OWNER/REPO/actions/jobs/<aggregate-job-id>/logs \
  --allow-escape-sequences | sed 's/\x1b\[[0-9;]*[a-zA-Z]//g' \
  | grep -E "\(infra: (true|false)\)|FINAL_VERDICT"
```

Read the token, not just the flag: `NEEDS_REVIEW` and `DID_NOT_RUN` take
different branches. The flag proves the aggregate called it infrastructure; it
does not say what failed.

The `infrastructure-failure` PR label is weaker evidence than it looks.
`check_infrastructure_failures.py` only adds it and never removes it, so it may
be left over from an earlier run.

For recovery, including why `gh run rerun --failed` cannot work here, see the
rate-limit memory named above.

## Evidence

Measured 2026-08-05 on two PRs whose diffs were memory files only.

| PR | Run | Agents infra:true | QA | Final verdict |
| --- | --- | --- | --- | --- |
| #4596 | 30969590662 | 9 of 10 | `PASS` (infra:false) | `DID_NOT_RUN` |
| #4593 | 30966540941 | 9 of 10 | `PASS` (infra:false) | `DID_NOT_RUN` |

Every one of those nine reported `NEEDS_REVIEW (infra: true)`, security among
them, which is row 1: category `INFRASTRUCTURE`, lines 106 to 108 fire, final
`DID_NOT_RUN`. No agent reported a per-agent `DID_NOT_RUN` in either run, so
rows 2 and 3 are read from the code, not observed here.

Security job 92190890958 (#4596) carries the `HTTP 403` above; #4593's job
92181726500 failed the same way.

All ten agent jobs concluded `success` while nine produced no verdict. Job
conclusion is not evidence a review ran.

Nine identical verdicts pointed at one shared cause here, confirmed by the
`HTTP 403` first error in each log. Do not invert that into a rule.
`NEEDS_REVIEW` is the default whenever a verdict is empty, so identical tokens
are equally consistent with agents failing for different reasons.

QA passing among nine infra failures is a scheduling artifact, not a partial
review; likely it ran after PR-diff retrieval recovered, which is inferred from
job ordering, not measured.

Both runs were re-run with no diff change and reached `attempt=2
conclusion=success`, 0 failing checks. That is consistent with the diagnosis,
not proof of it: the reviewers are not deterministic, so a clean rerun cannot
rule out a real finding. The `HTTP 403` is what proves infrastructure.

## Anti-Pattern

Reading `❌ AI Quality Gate FAILED / Agents with blocking verdicts:` as nine
findings and addressing them. The entries carry no text because no review
produced any. Equally wrong: taking `(Copilot CLI unavailable)` at face value
and debugging the CLI. Worst: concluding "all failures are INFRASTRUCTURE, so
the gate is buggy" and editing the gate. Check whether security is in the infra
set first. If it is, the block is the design.

## Related

- `github-rate-limit-payload-does-not-predict-service.md` (usual trigger, two refusal modes, recovery)
- `ci-infrastructure-003-job-status-verdict-distinction.md` (this is that distinction's sharpest instance)
- `ci-a-red-check-on-your-pr-may-be-inherited-from-main.md`
- `ci-infrastructure-001-fail-fast-infrastructure-failures.md`
