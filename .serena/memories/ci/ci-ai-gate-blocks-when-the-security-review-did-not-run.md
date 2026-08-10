# Skill: Why the AI quality gate blocks when security review did not run (92%)

## Statement

When `Aggregate Results` fails and nine or ten agents report the same verdict,
suspect one infrastructure failure reported many times before ten real ones.
The current contract after issue #4777 is:

- A security infrastructure failure produces `DID_NOT_RUN` and blocks.
- An unknown or malformed verdict remains `UNKNOWN` and blocks.
- An infrastructure failure outside security may downgrade to `WARN`.

Eureka: gate availability is gate correctness. Conventional CI advice treats
infrastructure outages as non-blocking. That fails for a required security gate:
no review means no evidence, so a green check is a false pass.

## The old failure message named a cause it never measured

Before issue #4777, three writers printed `Copilot CLI unavailable` for any
infrastructure category. Run 31283819979 disproved that diagnosis:

```text
Installing GitHub Copilot CLI@1.0.63...
GitHub Copilot CLI 1.0.63.
Error: Authentication token found but could not be validated.
Failed to fetch PAT user login (401): GitHub returned: Bad credentials
```

The binary was present. Authentication failed. Issue #4777 replaced the
invented cause with cause-neutral diagnostics. Read the first `##[error]` in
the agent job; the trailing summary is classification, not diagnosis.

## Why the per-agent job can succeed while the PR is blocked

Two different decisions. Reading the first as final is the trap.
`agent_review_check_verdict.py:49` starts the empty-verdict fallback and lines
52-55 derive an infra flag when both the verdict and the findings are empty.
The per-agent step returns 0 and defers PR status to `Aggregate Results`. The
verdict artifact still travels to the aggregate, which decides the gate.

`.github/scripts/aggregate_quality_verdicts.py` preserves `DID_NOT_RUN` when
security is `INFRASTRUCTURE` and every failure uses a recognized infrastructure
token. Unknown or unrecognized tokens remain `UNKNOWN`. Non-security
infrastructure-only failures may downgrade to `WARN`.

`scripts/quality_gate/check_critical_failures.py:55` blocks on `DID_NOT_RUN`:

```python
BLOCKING_VERDICTS = frozenset(FAIL_VERDICTS | {"UNKNOWN", "DID_NOT_RUN"})
```

## The token still decides the blocking reason

`get_category` classifies `FAIL_VERDICTS`, `UNKNOWN`, and `DID_NOT_RUN` as
`INFRASTRUCTURE` when the infra flag is true. The aggregate then distinguishes
recognized infrastructure tokens from malformed input.

| security | other agent | security category | final | blocks | warning |
| --- | --- | --- | --- | --- | --- |
| `NEEDS_REVIEW` + infra | `PASS` | `INFRASTRUCTURE` | `DID_NOT_RUN` | yes | yes |
| `DID_NOT_RUN` + infra | `PASS` | `INFRASTRUCTURE` | `DID_NOT_RUN` | yes | yes |
| `DID_NOT_RUN` + infra | `NEEDS_REVIEW` + infra | `INFRASTRUCTURE` | `DID_NOT_RUN` | yes | yes |
| `DID_NOT_RUN` + infra | `UNKNOWN` + infra | `INFRASTRUCTURE` | `UNKNOWN` | yes | yes |

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

`check_critical_failures.py:22-24` records the reason: issue #1934 added `UNKNOWN`
so a crashed or unparseable skill forces attention, and #2818 added
`DID_NOT_RUN` so an infrastructure failure that skips the review cannot pass.
Commit `426c1aa28` (#2846) made the behavior fail closed across gates and
hooks. Issue #2821 added visibility without changing merge semantics.

Commit `46da25783` in PR #4619 reversed that policy on 2026-08-05 and made
security infrastructure failures non-blocking `WARN`. Run 31283819979 then
showed the cost: all ten reviewers failed authentication and the required gate
passed. Issue #4777 restored the security block on 2026-08-08.

Never apply these edits:

- Removing `DID_NOT_RUN` from `BLOCKING_VERDICTS`.
- Widening the infrastructure `WARN` downgrade to cover security.

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
