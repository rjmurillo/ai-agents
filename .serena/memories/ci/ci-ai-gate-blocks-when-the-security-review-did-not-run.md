# Skill: Why the AI quality gate blocks on DID_NOT_RUN, and why its stated cause is hardcoded (92%)

## Statement

When `Aggregate Results` fails and nine or ten agents report the same verdict,
suspect one infrastructure failure reported many times before ten real ones.
Two incidents support the shape, not a base rate. In both, the gate refused to
certify a PR whose security review never ran. That refusal is deliberate but
not universal: one token combination passes such a PR silently (issue #4654).

`github-rate-limit-payload-does-not-predict-service.md` covers the usual
trigger and recovery. This covers what it does not: the summary line names a
cause nothing measured, the block is deliberate so repairing it removes a
security requirement, and the failing agent's verdict token decides whether
anything blocks.

## The failure message names a cause it never measured

`scripts/ci/agent_review_check_verdict.py:57` prints:

```text
⚠️ 🔒 security review had infrastructure failure (Copilot CLI unavailable)
```

`Copilot CLI unavailable` is a literal baked into the f-string, printed because
the code path is an infrastructure failure, not because anything diagnosed the
CLI. The same claim is hardcoded in `.github/scripts/generate_quality_report.py:162`,
`check_spec_failures.py:94`, and a comment in `agent-review/action.yml`, emitted
on fail-verdict infrastructure paths whatever actually broke.

The CLI is in fact probed, just not here and not as input to this message.
`scripts/ci/install_copilot_cli.py:70` runs `copilot --no-auto-update
--version`, and `.github/actions/ai-review/action.yml:177` can run
`diagnose_copilot_cli.py`. Neither result reaches the string above.

On the measured incident the CLI installed and answered `--version` earlier in
the same job. That proves it was present, not healthy; no reviewer call
succeeded:

```text
Installing GitHub Copilot CLI@1.0.63...
GitHub Copilot CLI 1.0.63.
##[error]Failed to fetch PR diff for #4596 from rjmurillo/ai-agents: could not
find pull request diff: HTTP 403: API rate limit exceeded for user ID 6811113
```

The review action then failed fetching the PR diff. The enclosing agent job did
not die: it saved results and concluded `success`. Read the first `##[error]`
in a failing agent job; the trailing summary is a template, not a diagnosis.
## Why the per-agent job says "Not blocking PR" while the PR is blocked

Two different decisions. Reading the first as final is the trap.
`agent_review_check_verdict.py:44` derives an infra flag when both the verdict
and the findings are empty. Line 55 prints "Not blocking PR." and line 60
returns 0. That is the per-agent step declining to fail itself, nothing more.
The verdict still travels to the aggregate, which decides the gate.

`.github/scripts/aggregate_quality_verdicts.py` has three outcomes. Lines 106
to 108 force `DID_NOT_RUN` when security is `INFRASTRUCTURE` and no agent is
`CODE_QUALITY`; security alone is enough, and the other axes may all be `PASS`.
Lines 109 to 111 downgrade to `WARN` when the remaining failures are
infrastructure and security is not among them. Any real code-quality failure
skips both and keeps the merged verdict.

`scripts/quality_gate/check_critical_failures.py:55` blocks on `DID_NOT_RUN`:

```python
BLOCKING_VERDICTS = frozenset(FAIL_VERDICTS | {"UNKNOWN", "DID_NOT_RUN"})
```

## The token decides the branch, and one combination blocks nothing

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
Row 2 still blocks, but through `UNKNOWN` in `BLOCKING_VERDICTS` rather than any
security rule, and prints no warning. Row 3 is a fail-open: security did not
run, the gate passes, and the warning meant to make that visible is suppressed.
Filed as issue #4654. So "an infra failure always blocks" is wrong: the
security-specific logic keys off a category only some failure tokens receive.

The tokens come from different writers. `NEEDS_REVIEW` is the empty-verdict
default at `agent_review_save_results.py:56-57`. `DID_NOT_RUN` is selected at
`check_ai_review_infra_gate.py:69` and written at line 119. Two more routes sit
outside this pair: `invoke_copilot_cli.py:218` emits `CRITICAL_FAIL` after
retry exhaustion, and `validate_artifact_download.py:83` returns 1 on a missing
artifact. A fifth blocks earlier still:
`scripts/quality_gate/load_review_results.py:132-134` returns 3 on an
unreadable or invalid-UTF-8 artifact, and its workflow step carries no
`continue-on-error`.

## Chesterton's fence: three edits that look like fixes

The asymmetry reads like an oversight. It is not.
`check_critical_failures.py:22-24` records the reason: issue #1934 added `UNKNOWN`
so a crashed or unparseable skill forces attention, and #2818 added
`DID_NOT_RUN` so an infrastructure failure that skips the review cannot pass.
Commit `426c1aa28` (#2846) made the behavior fail closed across gates and
hooks. The fence is #2818's, not #2821's. `230bb7cfc` names both in one
sentence, "preserve security review DID_NOT_RUN instead of downgrading it to
WARN", which reads as joint ownership and is the trap: the commit closing #2821
(`3c0b76429`) says "Merge semantics are unchanged". #2821 added only the
annotation at `aggregate_quality_verdicts.py:120`. So widening the `WARN`
downgrade reverts #2818, and a joint commit message does not say which issue
owns which half.

The remedy is the one the warning names: re-run the gate, or review security
manually. Do not change the gate logic. The two edits below turn the gate green
and remove the requirement that the security review happen. The warning still
prints, because it is driven by the aggregate's own `security_review_ran`, which
neither edit touches. So the PR merges green with the reason sitting unread in
the log. Never apply them:

- Removing `DID_NOT_RUN` from `BLOCKING_VERDICTS`.
- Widening the line 109 `WARN` downgrade to cover security.

A third edit is inert. Changing `_BLOCKING_VERDICTS` at
`agent_review_check_verdict.py:28` does not move the final gate outcome here:
`agent_review_save_results.py` already defaulted the empty verdict, set the
infra flag, and wrote the artifacts at lines 72 to 75, which `action.yml`
uploads at line 157 before the verdict check runs at line 187. The aggregate
reads those artifacts. That set still governs whether the agent step fails on a
real blocking verdict with no infra flag, so it is not dead code.

## Confirming the classification

The aggregate job logs a per-agent verdict and infra flag:

```bash
gh api repos/OWNER/REPO/actions/jobs/<aggregate-job-id>/logs \
  --allow-escape-sequences | sed 's/\x1b\[[0-9;]*[a-zA-Z]//g' \
  | grep -E "\(infra: (true|false)\)|FINAL_VERDICT"
```

Read the token, not just the flag: `NEEDS_REVIEW` and `DID_NOT_RUN` take
different branches. `infra:true` is the raw per-agent artifact flag, not the
aggregate's category, which `get_category` can still return as `N/A`. The
`infrastructure-failure` PR label is weaker still: `check_infrastructure_failures.py`
only adds it and never removes it, so it may be stale.

For recovery, including why `gh run rerun --failed` cannot work here, see the
rate-limit memory above.

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

Two caveats. `NEEDS_REVIEW` is the empty-verdict default, so identical tokens
are equally consistent with ten unrelated failures; the `HTTP 403` and the
per-agent `(infra: …)` flag are what prove infrastructure, not the agreement.
Both PRs went green on rerun with no diff change, which is consistent with the
diagnosis but cannot confirm it, since the reviewers are not deterministic.

## Anti-Pattern

Reading `❌ AI Quality Gate FAILED / Agents with blocking verdicts:` as nine
findings and addressing them. Those lines cannot tell you: `find_blocking`
returns `f"{name}: {verdict}"` and never reads findings, so a real
`NEEDS_REVIEW` prints what an empty infra default prints. The tells are
`infra: true` and the agent job's first `##[error]`. Equally wrong: debugging
the CLI on the strength of
`(Copilot CLI unavailable)`, or concluding the gate is buggy and editing it.
Check whether security is in the infra set first. If it is, the block is the
design.

## Related

- `github-rate-limit-payload-does-not-predict-service.md` (trigger, recovery)
- `ci-infrastructure-003-job-status-verdict-distinction.md` (sharpest instance)
- `ci-a-red-check-on-your-pr-may-be-inherited-from-main.md`
- `ci-infrastructure-001-fail-fast-infrastructure-failures.md`
