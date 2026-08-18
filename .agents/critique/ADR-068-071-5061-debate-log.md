# ADR-068 / ADR-071 issue #5061 debate log

## Summary

- Scope: the 2026-08-18 documentation amendments to ADR-068 and ADR-071
  reconciling their "current facts" prose with the `serena_memory_scope_guard`
  PreToolUse gate issue #5061 added to the consolidated dispatcher path. The
  underlying code change (the guard itself, its registration in
  `dispatch_groups.json`/`hooks.json`, and the regenerated Copilot artifacts)
  was already implemented and committed before this review; the review scope
  was the two ADR amendments and their supporting test fixes only.
- Rounds: 2. Round 1 was a full six-role parallel review. Round 2 re-checked
  the single outstanding Block vote (critic) against the fixes made in
  response to Round 1.
- Outcome: consensus. Architect flipped Block to Accept after a mechanical
  fix. Critic flipped Block to Disagree-and-Commit after a tracking issue was
  filed and one clarifying sentence was added. Independent-thinker, security,
  analyst, and high-level-advisor voted Disagree-and-Commit in Round 1 and
  were not re-polled; their reservations were addressed by the same fixes.

## Round 1: agent findings and votes

| Agent | Finding | Vote |
|-------|---------|------|
| architect | P1: lines 351 and 389 of ADR-068 still read "two shims" in Decision point 4 and the Alternatives Considered table, left stale while the Status paragraph, Re-evaluation Triggers section, and Consequences bullets were correctly updated to three shims in the same amendment. P2: the deferred re-affirmation names no tracking issue. | Block (P1 only; stated it would flip to Accept once corrected) |
| critic | P0-1: the ADR's own "Reopen this decision when any of these occurs" mandate fires (triggers 2 and 3), but the amendment cites no tracking issue, unlike the #4874 and #5013 precedents which each closed with a same-change re-affirmation. P0-2: the regression is stated as an abstract interpreter-start count (2 to 3 to 4) with no real latency or session-level frequency estimate. P1: no discussion of why a direct, non-consolidated host entry wasn't used for the new gate instead of joining (and collapsing) the union. P2: the trigger-3 wording change ("or collapses to no host matcher at all") is a substantive edit to a Decision Points list, bundled into what the amendment frames as a factual reconciliation. | Block |
| independent-thinker | P1: ADR-071's own 2026-08-11 amendment already rejected a lowercase-matcher variant for `require_subagent_model` specifically because an unreducible matcher "drops the host-level matcher entirely... (the #3075 regression)." Issue #5061 reintroduces that named regression without explaining why the same constraint didn't rule it out here too, or why the previously-established direct-registration alternative wasn't used. P2: no tracking issue for the deferred follow-up. Also verified the numeric and matcher-collapse claims directly against the generated artifacts (independently confirmed correct). | Disagree-and-Commit |
| security | MEDIUM-001: deferred re-affirmation with no cited issue, given the precedent of same-change re-affirmation on the prior two trigger firings. MEDIUM-002: "self-filter correctly" is asserted for the two pre-existing shims with no test citation. LOW-003: the timeout ceiling growth (100s to 110s, 105s to 115s host entry) is reported accurately but compounds an already-open "no evidence the host enforces this" residual; not new risk, just larger magnitude. No CWE-22/77/78/ASI0X pattern found. | Disagree-and-Commit |
| analyst | Independently re-derived every numeric claim from a fresh `build_all.py` run and the generator source (`generate_dispatcher.py`'s `_matcher_tool_tokens` / `event_matcher_union` / `dispatcher_entry`), confirming the causal chain (unreducible matcher poisons the union poisons the host entry) is implementation fact, not an assumption. P1: ADR-071's own `## Status` and `## Date` sections were not updated for the new amendment, unlike ADR-068's, though the detailed amendment body was added to both files. P2: no boundary test analogous to `test_adr_071_scopes_2026_08_11_and_2026_08_14_amendment_sections` exists for the new 08-14-vs-08-18 boundary; flagged as a gap, not blocking. | Disagree-and-Commit |
| high-level-advisor | The underlying containment fix should not be blocked on ADR paperwork; the ADR amendment is bookkeeping, not the guard itself. The actual finding: "tracked as follow-up" with no issue number is prose, not tracking, and is the first time this ADR's re-evaluation trigger has fired without a same-cycle resolution or a citable deferral artifact; landing it as-is risks the trigger mechanism degrading into a checkbox for future gate additions. Recommended filing the issue now (a five-minute fix) rather than blocking the merge on completing the full review. | Disagree-and-Commit |

## Phase 2: fixes applied between Round 1 and Round 2

1. Corrected ADR-068 lines 351 and 389 (Decision point 4, Alternatives
   Considered table) from "two shims" to "three shims," resolving architect's
   P1.
2. Filed issue #5151 (`rjmurillo/ai-agents#5151`) scoping the six-role
   re-affirmation review to: re-affirming or revising the
   consolidated-dispatcher decision, quantifying the regression (spawn
   latency and frequency multiplier, explicitly noting the only historical
   figure in the ADR, "246 ms Windows cold start," is marked HISTORICAL and
   superseded), formally weighing the two rejected alternatives, and citing
   (not asserting) that the two pre-existing shims' self-filtering is
   unaffected. Cited by number in both ADR-068 and ADR-071's 2026-08-18
   amendment paragraphs, replacing the bare "tracked as follow-up" prose.
3. Added an alternatives-considered paragraph to ADR-071's 2026-08-18
   section: a direct, non-consolidated host entry was not adopted because
   Decision point 2's reducibility rule applies independent of
   consolidation, so a standalone entry would also emit no host matcher for
   this MCP-tool pattern; full exclusion (the #5013 precedent) was not
   adopted because, unlike `push_pr_script_identity_guard` (no in-repo
   fallback, accepted zero Copilot coverage after a specific containment
   incident), it would leave Copilot sessions unprotected against the exact
   cross-worktree write bug issue #5061 fixes.
4. Narrowed the "self-filter correctly" claim in both ADR-068 and ADR-071 to
   what is actually verifiable without a new test: `markdownlint_guard` and
   `require_subagent_model`'s own code is unchanged by this diff, and
   Decision point 2 already documents in-process self-filtering as
   independent of the host union, so their behavior is unaffected by this
   amendment rather than newly re-verified by it.
5. Added an explicit statement in both ADR-068 and ADR-071 that no current
   measurement in this repository quantifies the spawn-frequency multiplier
   or per-spawn latency, assigning that measurement to issue #5151 rather
   than asserting a number.
6. ADR-071's P1 (missing Status/Date update) was fixed: added a "2026-08-18"
   paragraph to `## Status` and appended "2026-08-18" to `## Date`,
   mirroring every prior amendment's pattern.
7. Did not act on: security's LOW-003 (no new risk category, magnitude only,
   folded into #5151's scope); analyst's P2 (no new boundary test for the
   08-14-vs-08-18 section split; a gap, not a defect, in the established
   pattern); critic's P2 (trigger-3 wording change bundled with the metrics
   update; judged low severity, the wording change is itself a correction
   the new evidence demands, not a separate undisclosed decision).

## Round 2: critic re-poll

After the Phase 2 fixes, critic was asked whether citing a real, scoped
issue plus an explicit "no measurement exists, here is where it will be
produced" satisfies P0-2's request for a quantified regression, or whether
merge requires the number in hand.

Critic's verdict: Disagree-and-Commit. P0-1 resolved (issue #5151's body
covers exactly the four items critic would have demanded). P0-2 resolved on
the honesty question: citing the real gap and assigning it to a scoped
follow-up, rather than fabricating a figure, is the correct choice, and this
amendment documents an already-shipped guard rather than gating its
shipment, so blocking the paperwork does not change the regression's
existence. Reservation: the amendments should state plainly, not leave
implicit, that this is the first trigger firing in this ADR's history that
defers its re-affirmation rather than closing it in the same change. Fixed:
one sentence added to each ADR's 2026-08-18 section naming the deviation
from the #4874/#5013 precedent explicitly.

## Outcome

Final tally: 1 Accept (architect), 5 Disagree-and-Commit (critic,
independent-thinker, security, analyst, high-level-advisor), 0 Block. No
agent's final position asked for anything not yet applied to the working
tree at commit time.
