# ADR-099 Debate Log: Remove the commit-limit-bypass gate

**Decision under review**: ADR-099, removing the 20/40-commit block and the
human-only `commit-limit-bypass` label, keeping the `needs-split`
advisory label and the WARNING/ALERT notices at the same 10/15 thresholds.

**Authorization**: direct, explicit instruction from the repository owner
(rjmurillo) in-session on 2026-08-21: "get rid of gate requiring
commit-limit-bypass label."

**2026-08-21 correction: the sections below were a simulated pre-panel
pass, not the mandated review.** The paragraph originally here argued that
this ADR was not a heavy, hard-to-reverse decision and so did not need the
full six-role `adr-review` panel, and recorded a single author's simulated
version of each of the six perspectives instead of convening them. A
Copilot automated review on PR #5234 correctly rejected that reasoning:
`AGENTS.md` states "Any `ADR-*.md` edit fires adr-review" with no
carved-out exemption for reversible process changes, and a single author
narrating six roles is not a review, it is one perspective wearing six
labels; it cannot surface a disagreement the author did not already think
of. The sections immediately below ("Architect perspective" through
"Verdict") are kept, relabeled, as a record of that first, inadequate pass,
not deleted, per `.claude/rules/curating-memories.md`'s
correct-rather-than-silently-delete discipline. The real panel's findings
follow in the "Real six-role panel" section after them.

## Simulated pre-panel perspectives (superseded, kept for the record)

The subsections below were authored by one session narrating all six
roles itself, not by convening the panel. Read them as a single author's
guess at what six independent reviewers might say, already superseded by
the real panel below.

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

## Real six-role panel (2026-08-21)

A GitHub Copilot automated review on PR #5234 flagged that this ADR had not
gone through the mandatory `adr-review` panel, correctly citing `AGENTS.md`'s
"Any `ADR-*.md` edit fires adr-review" with no exemption. In response, the
`.claude/skills/adr-review/` skill was invoked for real: all six roles
(architect, critic, independent-thinker, security, analyst,
high-level-advisor) ran as independent agents against the full ADR-099 text
above, per the skill's Phase 0-4 protocol.

The panel's findings converged on two issues more consequential than
anything the simulated pass above surfaced, neither of which a
single-author simulation was positioned to find because both require
reading files outside this ADR:

1. **ADR-100 ("Retire the Pull Request Size Ceilings") and ADR-101
   ("Enforcement Planes") already exist on `origin/main`** (`status:
   proposed`, `implemented: false`, both dated 2026-08-20), decide the
   identical retirement question this ADR decides, and were uncited here.
   ADR-100 in particular reaches the same conclusion from a 292-PR measured
   population and three reconstructed blocking cases, far stronger evidence
   than this ADR's PR #5209/#4846 pair, and states two conditions ("Decision
   item 6" telemetry, a 90-day re-measure follow-up issue in its "Time-box"
   section) as necessary for its own retirement to be considered complete.
   Independently re-verified in this session: `git fetch origin main && git
   show origin/main:.agents/architecture/ADR-100-retire-pr-size-ceilings.md`
   and the ADR-101 equivalent both resolve to real, substantial files, not a
   stale reference.
2. **This ADR's Context section stated a false premise**: "an agent could
   not apply it to its own PR, only ask a maintainer to." Independently
   re-verified in this session: `git show
   origin/main:scripts/validation/git_hook_policy.py` lines 6062-6073 record
   in the code's own comment that "an agent applied the label to PR #4735 on
   2026-08-08 after this gate suggested it (issue #4782)," and that the
   human-only restriction added afterward is advisory text in a failure
   message, not a write-permission control. Both ADR-099's Context and its
   own Prior Art Investigation section already named issue #4782 by number,
   which should have been the tell; the simulated pass did not follow that
   citation back to what #4782 was actually responding to.

Both findings are corrected directly in ADR-099's body (Context, Related
Decisions, References) rather than only recorded here. A third, lower-severity
finding (two script docstrings, `scripts/ci/enforce_pr_validation.py` and
`scripts/validation/pr_commit_count.py`, misattributing the CI-side gate's
removal to the same session-sandboxing failure that motivated the local
pre-push gate's removal, when the CI job runs under a working `GH_TOKEN` and
never had that failure) was corrected in the same PR, independently verified
by reading both files and by tracing the deleted
`scripts/validation/check_pr_bypass_label.py`'s pre-deletion docstring via
`git show 9afc68381~1:scripts/validation/check_pr_bypass_label.py`.

A fourth item the panel raised, not a defect but a gap: neither this ADR nor
its implementation ships push-ceiling telemetry or a 90-day re-measure
commitment of the kind ADR-100 requires. `status: accepted` is kept per
explicit agent guidance against inventing a new frontmatter enum value for
"accepted, pending a follow-up commitment" (ADR-073 defines the enum as
`proposed | accepted | rejected | deprecated | superseded`); the gap is
closed instead with a "Confirmation and Reversal Triggers" section added to
the ADR body and two follow-up issues filed at merge time.

No panel role returned Block. The convergent verdict was Accept, conditioned
on the corrections above landing in the same change, which they do.
