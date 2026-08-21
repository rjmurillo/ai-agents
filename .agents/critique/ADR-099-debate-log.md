# ADR-099 Debate Log: Remove the commit-limit-bypass gate

**Decision under review**: ADR-099, removing the 20/40-commit block and the
human-only `commit-limit-bypass` label, keeping the `needs-split`
advisory label and the WARNING/ALERT notices at the same 10/15 thresholds.

**Authorization**: direct, explicit instruction from the repository owner
(rjmurillo) in-session on 2026-08-21: "get rid of gate requiring
commit-limit-bypass label." This is not a heavy, hard-to-reverse
architectural decision (it deletes an enforcement mechanism and its dead
supporting code; reverting is one revert away and the advisory signal it
replaces is unchanged), so this log records the reasoning that would be
raised by each debate perspective rather than convening the full six-role
panel `.claude/skills/adr-review/` runs for genuinely contested ADRs. The
2026-08-17 governance retrospective independently found that the full panel
was being over-applied to exactly this class of reversible process change
(`.agents/retrospective/2026-08-17-governance-bureaucracy-critical-review.md`,
"ADR audit" finding).

## Architect perspective

The block's enforcement point (a local pre-push hook shelling to `gh`) was
never able to be more available than the credentials of the session running
it. That is a structural placement problem, not a tunable threshold: no value
of `BLOCK_THRESHOLD` fixes a check that cannot always reach GitHub. The
correct fix is to remove the enforcement point, not harden it, because
hardening it (e.g., trusting an agent-supplied attestation) reintroduces the
self-bypass risk issue #4782 already closed once. Concurs with the decision.

## Critic perspective

The strongest objection: removing the hard stop means a genuinely
unreviewable PR (the PR #908 shape this cap was built to prevent) no longer
gets blocked by git. This is real and not fully mitigated. The mitigation
that exists: `needs-split` still auto-applies at the same 10/15 thresholds,
and it is visible on the PR to any reviewer, so the signal is not silent, it
is merely not machine-enforced. Accepts the decision on the condition that
the advisory signal is preserved, which it is (this ADR's Impact table keeps
`pr_commit_count.py`'s WARNING/ALERT classification unchanged).

## Security perspective

The removed check was a fail-closed control (on ambiguity, deny) protecting
against unbounded PR growth, not against a malicious actor; a PR's commit
count is not an attacker-controlled security boundary; the label being
human-only protected against an agent self-granting a bypass, not against
external compromise. Removing an availability-fragile advisory control is a
lower-risk change than removing an authorization or input-validation control
would be. No objection on security grounds, conditional on the human-only
label concept staying intact for the *other* gate that still uses the same
shape (`description-validation-bypass` in `scripts/validation/pr_description.py`,
untouched by this ADR).

## Independent-thinker perspective

Raises the alternative recorded in ADR-099's "Alternatives Considered" table:
fix the actual root cause (the Claude GitHub App is not connected for this
org, so `gh`/API calls are denied in cloud sessions while MCP tool access
works) rather than removing the gate. Correct as a complementary fix, but
insufficient as a substitute: connecting the app does not help a contributor
whose own token is rate-limited or revoked, and the gate's own docstring
already treats "gh denied" as an expected, not exceptional, condition it must
survive. Recorded as a parallel, out-of-repo action, not a reason to keep the
gate as designed.

## High-level-advisor perspective

The cost actually observed was not hypothetical: PR #5209 (this session,
reproduced directly: `gh api` 403 "GitHub access is not enabled for this
session") and PR #4846 (2026-08-17 retrospective, self-admitted
`commit-limit-bypass`/`needs-split` as symptoms of review-driven PR spin) both
show the same failure paying out in wasted agent turns and, in the #5209
case, an entire spun-up second branch and PR. Removing the gate stops paying
that cost immediately; the risk it reintroduces (an unreviewable mega-PR) is
bounded by the surviving advisory signal. Net positive.

## Verdict

**Accept.** No perspective raised a blocking objection. The critic's
condition (advisory signal preserved) and the independent-thinker's
complementary suggestion (connect the GitHub App) are both recorded in
ADR-099 rather than dropped.

## Post-accept correction

ADR-099 and several implementation files initially cited "#5230" as the
tracking issue for this change. #5230 is an unrelated draft PR opened by a
different session the same day (hitting the identical gh-403 wall this ADR
describes, on PR #5209's own stack), not an issue. The independent-thinker's
suggested root-cause fix was filed as issue #5232; the tracking issue for
this change itself was filed as issue #5233 once the citation error was
caught. All "#5230" references were corrected to "#5233".

## Post-accept correction 2: stale fetch-depth claim

ADR-099's Consequences and Impact sections both stated that the CI job's
`Checkout repository` step no longer needed `fetch-depth: 0` and that
dropping it would save an unshallow fetch on every PR-validation run. That
was true of an early implementation draft, which was reverted before merge:
the merge-tree ratchet and several count ratchets running later in the same
job also read `origin/main`'s trunk and depend on unshallow history
independently of the commit-count gate. The shipped `pr-validation.yml` keeps
`fetch-depth: 0`. PR #5234's automated spec validator caught the mismatch
between the ADR's prose and the actual diff after the initial push; both
passages are corrected to state that the step stays and that no fetch
savings materialize from this change.
