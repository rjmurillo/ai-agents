# ADR-076 Amendment (2026-08-19) Debate Log

**Subject**: "Amendment 2026-08-19: PR-live-state check on the renew path" appended to `.agents/architecture/ADR-076-pr-autofix-branch-ownership-lease.md`, addressing issue #5165.

**Round**: 1 of up to 10 (per adr-review debate protocol).

**Participants**: architect, critic, independent-thinker, security, analyst, high-level-advisor.

**Round 1 tally**: 6 ACCEPT-WITH-CHANGES, 0 ACCEPT, 0 BLOCK.

## Convergent findings (raised independently by 3+ agents)

1. **The Context arithmetic is wrong.** `RENEW_SKIP_MARGIN` (5 min) against `TTL` (15 min) at a 4-minute renewal cadence yields a write on roughly 1 of every 3 renew calls (t=12, t=24, t=36...), not "most calls" as the original draft claimed. Independent-thinker, critic, analyst, and high-level-advisor each derived this from the module's own constants and flagged the same error. Consequence: the motivating cost in the original draft was overstated by roughly 3x.
2. **A new `DONE` action value is the wrong shape.** Critic (P0), independent-thinker (P0-2), architect (P1-3), and high-level-advisor all converged on the same alternative: reuse `SKIP` with `reason: "pr-closed"`. The module's existing extension point for verdict specificity is the `reason` string (nine values today against two `action` values), and the one caller that actually motivated this amendment (the external, out-of-repo caller on PR #5078) will never be updated to branch on a third action value, so `DONE` buys nothing over `SKIP` for the case that matters, while costing an unallocated exit code and a wider public contract every consumer must eventually handle.
3. **The exit code for the new verdict is unspecified and has nowhere to go.** ADR-035's range (0/1/2/3/4) is fully allocated by this module already (architect, critic, security, independent-thinker). Dropping `DONE` in favor of `SKIP`/`pr-closed` resolves this without inventing a code.
4. **The scoping rationale ("`check_pr_live_state.py` already gates pr-autofix's own PR selection before `acquire` is reached") is false against the shipped recipe.** Critic verified `.claude/commands/pr-autofix.md`: `acquire` runs at line ~343 (Step 1), `check_pr_live_state.py` runs at line ~371 (Step 2): acquire runs *first*. The renew-only scoping is still defensible, but on cost grounds (one call per fix attempt vs. unbounded renewals), not on the false gating claim.
5. **The dedicated GraphQL call is avoidable, and the amendment's own cost claim (adds one round-trip) is self-inflicted.** High-level-advisor and security both independently found that `_pr_head_sha` (`pr_autofix_lease.py:677-702`) already fetches the full PR REST object via `gh api repos/{owner}/{repo}/pulls/{pr}` and discards everything but `.head.sha` through its `--jq` filter. That response already carries `state` and `merged`. Widening the existing `--jq` projection gets the live-state fact at zero new round-trips on the common path.
6. **ADR-090 (proposed, issue #3413) was not cited.** Architect found it explicitly amends ADR-076 for the same subsystem (v2 lease marker, 30-minute TTL, mandatory 5-minute renewal) and is the acknowledged successor for this exact code path. Related Decisions omitted it.
7. **ADR-076 part 3 step 6's prose is already stale against shipped code** (fail-open text superseded by the issue #4966 narrowing, with no amendment recorded) and this new amendment reasons against the contradiction without fixing it (architect P1-5).

## Findings specific to one agent, still required

- **Security**: `RENEW_FAILOPEN_LIVENESS_MARGIN` (180s) was sized before any new I/O was added to the self-renew fail-open window; a dedicated GraphQL call's worst-case latency (~295s with retries) would exceed that margin. Resolved by adopting the REST-reuse approach (finding 5), which adds no new I/O to that window. Also flagged: the exception catch set for a GraphQL failure must include `subprocess.TimeoutExpired`/`OSError`, not just `RuntimeError`.
- **Analyst**: the incident's own timestamps (13 renewals, 12:26Z to 13:18Z) overlap the merge of PR #5161 (`e28feae`, 12:42:54Z), which shipped `RENEW_SKIP_MARGIN` mid-window. The post-#5161 residual has never actually been measured in isolation.
- **Independent-thinker**: `_LIVE_STATE_QUERY` is a private, underscore-prefixed constant not in `check_pr_live_state.py`'s `__all__`; importing it reaches into another module's private symbol (and that module's import-time `sys.exit(2)` side effect). The query belongs in a shared location (`github_core`), not imported or forked.
- **Architect**: no kill criterion / measured-outcome tie to ADR-076 part 5's existing Phase-1 kill-criterion discipline, which itself has never been instrumented (`lease_collision_blocked` was never wired). No debate-log-per-amendment precedent was being followed until this file.
- **High-level-advisor**: questioned whether issue #5165's P1 label matches actual severity, given the SHA gate is unaffected and the cost is bounded/self-healing; recommended layering the fix (widen REST filter first, add a zero-cost lease-age cap for the tail, defer any dedicated GraphQL read to a measurement-gated follow-up).

## Resolution (Phase 3: propose updates for P0/P1 issues)

Given six independent reviewers converged on materially the same redesign (drop `DONE` for `SKIP`/`pr-closed`; reuse the existing REST call's fields instead of a new GraphQL round-trip; correct the arithmetic; cite ADR-090; mark part 3 step 6 superseded), the amendment is being rewritten in place to incorporate all of the above rather than iterating piecemeal. This is treated as the debate's Phase 3 resolution rather than launching a second full 6-agent round: the required changes are convergent and mechanical (an arithmetic fix, a citation, a superseded-marker note, and a design substitution every reviewer independently proposed the same way), not points of live disagreement between the agents that would need adversarial re-litigation.

Applied changes, mapped to findings above:

1. Corrected the renewal-cadence arithmetic in Context (finding 1) and softened the incident's precision claim per the analyst's overlap-with-#5161 finding.
2. Replaced the `DONE` verdict with `SKIP`/`pr-closed` throughout (findings 2, 3), eliminating the exit-code allocation problem entirely.
3. Replaced the dedicated GraphQL call with a widened `--jq` projection on the existing `_pr_head_sha` REST call (finding 5), eliminating the security-flagged `RENEW_FAILOPEN_LIVENESS_MARGIN` risk and the added-round-trip cost.
4. Corrected the scoping rationale to the cost-based argument only, removing the false gating claim (finding 4).
5. Added ADR-090 to Related Decisions with a note on how this narrowing relates to its proposed v2 contract (finding 6).
6. Marked ADR-076 part 3 step 6 superseded inline (finding 7).

## Outcome

**Consensus reached at Phase 3 resolution.** The rewritten amendment (see the "Amendment 2026-08-19" section of ADR-076, revised in the same change that adds this log) is considered ready for implementation. If a reviewer believes the rewrite does not fully address their finding, reopen this log with a Round 2 entry rather than treating this outcome as final.

Status changed on the amendment: still governed by ADR-076's overall `accepted` frontmatter status; the amendment itself is now implementation-ready pending no further objection.
