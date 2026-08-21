---
id: ADR-099
status: accepted
date: 2026-08-21
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
---

# ADR-099: Remove the commit-count block and its commit-limit-bypass label

## Status

Accepted

## Date

2026-08-21

## Context

`pr-validation.yml` and the local `push-ref-policy` pre-push hook
(`scripts/validation/git_hook_policy.py`) blocked a push or a merge once a
branch carried more than 20 authored commits against `origin/main` (or 40 when
the branch merged main, the "main-merge relief" from issue #3596). The only
sanctioned relief was a human-only `commit-limit-bypass` label
(CONTRIBUTING.md, "Bypassing the Limit"); an agent could not apply it to its
own PR, only ask a maintainer to.

The mechanism that enforced this locally could not reliably verify its own
escape hatch. `scripts/validation/check_pr_bypass_label.py` shells out to
`gh api` to read the PR's labels before allowing an over-limit push. In a
Claude Code cloud/remote session, `gh` and any direct GitHub REST call are
denied at the proxy level ("GitHub access is not enabled for this session"),
reproduced directly in this session:

```
$ gh api "repos/rjmurillo/ai-agents/pulls/5209" --jq '{number, state, labels}'
{"message":"GitHub access is not enabled for this session. An org admin must
connect the Claude GitHub App for this organization.", ...}
```

This is not a flaky, retryable failure; it is a structural property of that
class of session (the harness ships separate, working GitHub MCP tool access,
but nothing a git-hook subprocess can reach). The check's own docstring
already documents hitting exactly this on 2026-08-20 and improved only the
error *message*, not the underlying trust model, because a fail-open repair
would let anyone dodge the cap by claiming `gh` was broken.

The result, observed directly on PR #5209 (`commit-limit-bypass` label already
correctly applied by a human maintainer, per its label list) and independently
in PR #4846 (flagged in the 2026-08-17 governance retrospective as a
"review-driven PR spin" case that self-admits both `needs-split` and
`commit-limit-bypass`): a session whose local `gh` access is denied cannot
verify a label that is already true, so the hook fails closed and blocks the
push regardless. The only path the check itself offers when this happens
(`_describe_gh_failure`: "Split the PR, or ask a human maintainer") does not
fit a PR that is *already* labelled; the workaround a prior session actually
took was to open an entirely new stacked branch and PR (the legitimate
`_unpushed_commit_count` relief from issue #3610) purely to route around a
verification failure, not a real policy violation. That is a full PR review
cycle spent on infrastructure the gate could not see past.

## Decision

Remove the commit-count **block** and the `commit-limit-bypass` label
mechanism entirely, from both the CI workflow (`pr-validation.yml`,
`scripts/ci/enforce_pr_validation.py`) and the local pre-push hook
(`scripts/validation/git_hook_policy.py`). `scripts/validation/pr_commit_count.py`
keeps classifying commit counts into `OK` / `WARNING` (>=10) / `ALERT` (>=15),
and the `needs-split` label keeps getting applied/removed at those same
thresholds, but neither status blocks a push, a merge, or requires a label.
`scripts/validation/check_pr_bypass_label.py` (only ever called for this gate
and its `needs-split` soft-relief) is deleted, along with the
main-merge-relief plumbing (`main_first_parent_shas`, `contains_main_merge`,
`ReliefEvidence`, `main_merge_evidence`) that existed solely to compute the
raised 40-commit ceiling.

Authorized directly by the repository owner in-session (2026-08-21): "get rid
of gate requiring commit-limit-bypass label."

## Prior Art Investigation

### What Currently Exists

- **Structure being changed**: the 20/40-commit block in
  `scripts/validation/pr_commit_count.py` (`BLOCK_THRESHOLD`,
  `MAIN_MERGE_BLOCK_THRESHOLD`), enforced in `scripts/ci/enforce_pr_validation.py`
  and mirrored locally in `scripts/validation/git_hook_policy.py::_check_commit_limit`.
- **When introduced**: issue #362 (original 20-commit cap, following the PR
  #908 retrospective on unreviewable PR sprawl); issue #3596 (40-commit
  main-merge relief); issue #3610 (stacked-PR unpushed-commit relief); issue
  #3895 (needs-split small-fix-commit relief); issue #4782 (human-only label
  guidance after an agent self-applied the label to PR #4735).
- **Original author and context**: a direct response to PR #908 growing to 59
  commits and 228+ review comments because an unscoped `markdownlint --fix`
  reformatted the whole memory tree into the diff.

### Historical Rationale

PR #908's failure was real: an unreviewable PR is a real cost, and a hard cap
forces a conversation before a branch grows unmanageably large. The cap's
authors also anticipated legitimate large-but-atomic changes (the main-merge
relief, the stacked-PR relief) and tried to keep an escape hatch auditable by
making it human-only rather than agent-applied.

### Why Change Now

The original problem (unscoped tooling silently exploding a diff) was fixed
directly by the PR #908 remediation (scoped `markdownlint --fix`) and remains
fixed independently of this gate. What has not held up is the *enforcement*:
a hard block whose only relief requires a fact (a GitHub label) that a
harness-class of session structurally cannot verify locally converts "split a
genuinely oversized PR" into "improvise an expensive workaround to route
around a verification failure that has nothing to do with the PR's merits."
The risk of removing the block is that a genuinely unreviewable PR no longer
gets a hard stop; the mitigating fact is that the `needs-split` advisory label
and the WARNING/ALERT notices still fire at the same 10/15 thresholds, so the
signal to a reviewer or an author is unchanged. The block was the part that
required a label a local check could not confirm; the notice never did.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| Keep the block; teach the local check to also accept a pre-fetched attestation from the calling agent (e.g., GitHub MCP tool output written to a file) | Preserves a hard stop for genuinely oversized PRs | Introduces a new, unaudited trust boundary: a subprocess check trusting an agent-supplied claim about GitHub state is exactly the "agent self-applies its own bypass" failure issue #4782 already fixed once | Rejected: widens the attack surface the human-only label was built to close |
| Keep the block; fix the root cause instead (connect the Claude GitHub App for this org so `gh`/API calls work in cloud sessions) | Fixes the actual gap, no policy change needed | Org-level admin action outside this repo's code; does not help contributors on other harnesses/tokens that hit the same denial for unrelated reasons (rate limits, revoked PATs); the gate's own docstring already treats "gh denied by policy" as expected, not a bug to route around locally | Recorded here as the complementary fix, not a substitute: it does not change that a *local* check inherently cannot be more available than the credentials of the session running it, so the gate remains fragile even after the connector is fixed |
| Remove the block, keep the advisory notices (this decision) | Removes the one-sided failure mode (blocks the well-behaved case, never blocks the bad case once a human clicks the label); needs-split/WARNING/ALERT signal is unchanged | A genuinely unreviewable 60-commit PR no longer hard-stops | Chosen: the signal survives, the false block does not; owner-authorized directly |

### Trade-offs

The block's value was forcing a conversation before a PR became unreviewable.
That value is preserved by the advisory `needs-split` label and the
WARNING/ALERT notices, which fire at the same thresholds and are visible on
the PR and in the workflow log. What is lost is the hard stop for an author
who ignores the notices; what is gained is that the check can never again
block a well-behaved PR (label already correctly applied) purely because the
harness running the check has no GitHub credentials.

## Consequences

### Positive

- No PR can be blocked by an unverifiable label again; the fail-closed
  behavior that caused PR #5209's local push failure and PR #4846's spin
  cannot recur, because there is no block left to fail closed on.
- `scripts/validation/check_pr_bypass_label.py` and the main-merge-relief
  plumbing (`contains_main_merge`, `ReliefEvidence`, `main_merge_evidence`,
  `main_first_parent_shas`) are deleted rather than left as dead code guarding
  nothing.
- The CI job's `Checkout repository` step no longer needs `fetch-depth: 0`
  (it existed only to read `origin/main`'s trunk for the 40-commit relief),
  saving an unshallow ~165 MiB fetch on every PR-validation run.

### Negative

- A genuinely unreviewable, very large PR no longer gets a hard merge block.
  Mitigated: `needs-split` still auto-applies at the same 10/15-commit
  thresholds, and the retrospective and PR-review skills still analyze and
  recommend splits for such PRs; the recommendation is no longer enforced by
  git.

### Neutral

- The org-level root cause (the Claude GitHub App not connected for this
  organization, so `gh`/direct API calls 403 in cloud sessions while GitHub
  MCP tool access works) is unaffected by this change and remains a separate,
  optional fix outside this repository's code.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|---|---|---|---|
| `scripts/ci/enforce_pr_validation.py` | Direct | Drop the `commit_status == "BLOCKED"` branch and the label fetch | Low |
| `scripts/validation/git_hook_policy.py` | Direct | Drop `_check_needs_split_bypass`, main-merge-relief helpers; `_check_commit_limit` becomes advisory-only | Low |
| `.github/workflows/pr-validation.yml` | Direct | Drop `COMMIT_STATUS`/`COMMIT_LIMIT` env vars, the `BLOCKED` condition on the needs-split step, and the `fetch-depth: 0` unshallow checkout | Low |
| `scripts/validation/check_pr_bypass_label.py` | Direct | Deleted (only caller was the removed block) | Low |
| `CONTRIBUTING.md`, `.claude/skills/ai-agents-change-control/references/gate-ladder.md`, `AGENTS.md`, critic agent prompts | Documentation | Describe the gate as advisory-only; remove human-only-label instructions | Low |
| Tests (`tests/validation/test_pr_commit_count.py`, `tests/test_check_pr_bypass_label.py`, `tests/ci/test_pr_validation_workflow.py`, `tests/validation/test_git_hook_policy_atomic_commit.py`, `tests/workflows/test_pr_validation_needs_split.py`, `tests/validation/test_human_only_label_guidance.py`, `tests/test_lefthook_integration.py`) | Direct | Updated or deleted to match the advisory-only behavior | Medium (coverage of the removed block must not silently vanish; replaced with coverage of the advisory path) |

## Implementation Notes

Implemented in the same change as this ADR. See the PR this ADR ships with for
the exact diff; `scripts/validation/pr_commit_count.py`'s module docstring
carries the same rationale for a reader who lands there without this file.

## Related Decisions

- Supersedes the enforcement half of the informal policy recorded in
  CONTRIBUTING.md "Commit Count Thresholds" / "Bypassing the Limit" (issue
  #362, #3596, #3610, #3895, #4782). The advisory notice half is unchanged.

## References

- Issue #362 (original thresholds), #3596 (main-merge relief), #3610
  (stacked-PR relief), #3895 (needs-split small-fix relief), #4782 (human-only
  label guidance), #5230 (this removal).
- `.agents/retrospective/2026-08-17-governance-bureaucracy-critical-review.md`,
  which independently flagged PR #4846's `commit-limit-bypass`/`needs-split`
  labels as a "review-driven PR spin" symptom, and which argues the full
  six-role `adr-review` debate is reserved in principle for genuinely
  hard-to-reverse decisions; this one is a straightforward, reversible
  gate removal authorized directly by the repository owner, not run through
  the full panel.
- PR #5209, where this failure was reproduced live in this session.
