# ADR Debate Log: ADR-052 Template Strategy for Multi-Platform Agent Distribution

## Summary

- **Rounds**: 3 (Round 1: Phase 1 independent reviews, consolidated and resolved by session; Round 2: Phase 4 convergence check, all six agents re-invoked against the edited text; Round 3: a second Phase 4 convergence check, triggered by further edits made after Round 2's vote)
- **Outcome**: Consensus reached in Round 2 and reconfirmed in Round 3 (each: 1 Accept, 5 Disagree-and-Commit, 0 Block); Round 3 is the acceptance evidence for the current text
- **Final Status**: Accepted (status: accepted, implemented: false); supersedes ADR-036 (status: superseded, implemented: true)

## Context

Issue #5192 found ADR-052 (then `Proposed. Supersedes ADR-036.`) dangling-superseded ADR-036 (`Accepted`, no reciprocal marking). The repository owner made a sovereign decision, relayed through this session and not open to re-litigation in this debate: **accept ADR-052, supersede ADR-036.** A prior AI session had recommended the opposite (reject ADR-052) on the same evidence; the owner overruled that recommendation. This debate's scope was therefore not "should ADR-052 be accepted" but "what does recording that decision honestly and safely require."

## Round 1: Phase 1 Independent Reviews

| Agent | Verdict | Key Finding |
|-------|---------|-------------|
| **Architect** | NEEDS_CHANGES | ADR-073's acceptance-evidence binding unmet; bare status flip on ADR-036 inverts #5192's own bug (superseded-but-live with no callout); prose `## Status` must reconcile with frontmatter |
| **Critic** | NEEDS_REVISION | ADR-052's Prior Art section misdescribes ADR-036 (claims Claude agents were templated/generated; ADR-036:45 says the opposite) and never engages ADR-036's own rebuttal of the similarity metric (§Intentional Divergence, 204-209); six stale/false statements in ADR-052; five canonical files + generated mirrors assert "ADR-036, Accepted" |
| **Independent-Thinker** | Conditional accept | No automated consumer parses ADR status prose today, so the mechanical blast radius is smaller than briefed, but 61 files reference ADR-036 and six lines assert its status as fact to a *reading* agent; Phase 2 of ADR-052 ("remove templates/agents/") is an executable-looking instruction against a still-live pipeline |
| **Security** | APPROVED (no blocking findings) | No auth/secrets/execution surface in either ADR; the debate-log gate itself is weak (substring match, no verdict parsing) but that is pre-existing and not worsened by this change; recommends the transition be documented as an authorization, not dressed as organic consensus |
| **Analyst** | Conditional accept | ADR-052's file counts stale (21/23 vs live ~31/32); `.claude/rules/templates.md`-class binding instructions and governing-ADR pointers in `templates/README.md`, `templates/AGENTS.md`, `src/claude/AGENTS.md` will contradict the flip; issue #124 (ADR-052's tracker) is closed, no successor exists |
| **High-Level-Advisor** | Conditional accept (named block condition) | Ship the flip plus every claim the flip falsifies, nothing more; explicit non-negotiable: block if any of six status-asserting citations still reads "Accepted"/"Governing ADR" after merge; a new tracking issue is the only real forcing function (a `review-by` field has no reader) |

All six independently converged on the same shape without cross-agent visibility (each ran in a separate isolated session): frontmatter + `implemented` field split, a first-screen "still operative" callout on both files, correction of stale facts, repair of status-asserting citations (not content-describing ones), a debate-log artifact, and a fresh tracking issue.

## Consensus Points

1. The owner's decision is recordable and reciprocal frontmatter/prose is the right instrument (all 6).
2. `status: accepted` + `implemented: false` on ADR-052, `status: superseded` + `implemented: true` on ADR-036 is the correct pairing, mirroring ADR-098's established split-field precedent (all 6).
3. A bare status flip with no "still operative" callout on ADR-036 recreates #5192's exact bug, inverted: a superseded record whose governed machinery (31 `templates/agents/*.shared.md` files, `build/generate_agents.py`, lefthook `generate-agents` job, `validate-generated-agents.yml`, `agent-drift-detection.yml`) is still fully live (architect, critic, independent-thinker, high-level-advisor: 4 of 6, security and analyst concurred in discussion of scope).
4. ADR-052's Migration Plan Phase 2 ("remove `templates/agents/`") must not read as authorized by this change; the callout must say so explicitly (architect, independent-thinker, high-level-advisor).
5. Six specific status-asserting citations must be corrected in the same change, and their generated Copilot mirrors regenerated (not hand-edited): `.claude/agents/AGENTS.md` (byte-identical twin `src/claude/AGENTS.md`), `.claude/skills/ai-agents-architecture-contract/SKILL.md`, its `references/provenance.md`, `.claude/skills/ai-agents-generation-and-release/SKILL.md`, `templates/README.md`, `templates/AGENTS.md` (architect, critic, analyst, high-level-advisor, independent-thinker: 5 of 6; security concurred it is the "content vs status" line to hold).
6. Content-describing citations of ADR-036 (the synchronization procedure itself, the "MANUAL - not auto-synced" markers) stay untouched: the procedure is still what runs (high-level-advisor's "status claims versus content claims" framing, adopted by consensus).
7. Issue #124 is closed and covers only "write the ADR," not delivery; a successor tracking issue is required, referenced from ADR-052's Implementation Status (all 6).
8. `.agents/critique/ADR-052-debate-log.md` (this file) satisfies ADR-073's acceptance-evidence requirement; without it, `status: accepted` is a forgeable hand-edit per ADR-073's own governing text (architect, critic, security, high-level-advisor, independent-thinker: 5 of 6 raised this explicitly).

## Points Not Adopted (scope discipline)

- Rewriting ADR-052's Migration Plan to the correct 6-surface topology: deferred to the new tracking issue (all 6 explicitly flagged this as out of scope for a reciprocity fix: "ocean, not lake").
- Backfilling ADR-073 frontmatter on the ~58 other frontmatter-less ADRs in the corpus: explicitly out of scope (high-level-advisor, architect).
- A `review-by` frontmatter field: rejected: no consumer reads it today (high-level-advisor).
- Touching `lefthook.yml`, the CI workflows, `detect_agent_drift.py`, or `check_agent_content_parity.py`: explicitly out of scope; none of these enforce ADR-036 by citation (independent-thinker verified `check_agent_content_parity.py` cites `GENERATOR-FILES.md`/REQ-003-010, never ADR-036: a prior-session claim to the contrary was corrected).
- Re-measuring the 2025-12-15 drift-analysis numbers ADR-052 relies on: flagged as stale (~8 months) by high-level-advisor and critic, but re-measurement belongs to the new tracking issue, not this reciprocity fix.

## Dissenting Views (Disagree-and-Commit)

**Critic** and **independent-thinker** both noted that ADR-052's core evidentiary claim (2-13% similarity as proof of "failure") is directly rebutted, in advance, by ADR-036 §Intentional Divergence (written 2026-01-01, before ADR-052's 2026-03-01 evidence table) and that ADR-052 never engages that rebuttal. The owner's decision stands regardless (Sovereignty), but the record should not let the rebuttal disappear silently: ADR-052's Status section states that ADR-036's Intentional Divergence reading is preserved and not contested by this acceptance, rather than implicitly overruled by omission. Independent-thinker also dissents that "accept the direction, not yet the migration" is one defensible reading of the owner's instruction but not the only one; the ADR text is written so both readings converge on the same safe action (no deletion authorized by status alone).

## Round 1 Positions (synthesized by session from Phase 1 verdicts, not cast against the edited text)

Relabeled 2026-08-25 per a Copilot review finding on PR #5286: this table was session-synthesized from each agent's Phase 1 independent review, before the ADR edits existed to vote on. It records what each agent's Phase 1 findings implied their position would be once their approval conditions were met, not an actual vote against final text. The real Phase 4 convergence check, with each agent re-invoked against the edited files, is recorded in "Round 2" below; that table is the acceptance evidence ADR-073 requires, not this one.

| Agent | Synthesized Position | Notes |
|-------|----------|-------|
| architect | Disagree-and-Commit | Approval conditions (debate log, callouts, prose reconciliation, tracking issue, citation repair) must all land in this change; accepts the pairing is structurally sound once they do |
| critic | Disagree-and-Commit | Same conditions; also wants the Intentional Divergence rebuttal acknowledged, not silently overruled |
| independent-thinker | Disagree-and-Commit | Reservations on migration-plan staleness and ambiguity of "accept" scope remain; documented via the explicit non-deletion callout |
| security | Accept | No blocking findings; recommends the debate-log gate itself (substring match) be hardened in a future, separate change |
| analyst | Disagree-and-Commit | Wants live counts corrected and binding cross-references repaired; satisfied by the citation-repair task list |
| high-level-advisor | Disagree-and-Commit | Named block condition (any of six status citations left stale) must not occur; otherwise accepts |

## Round 2: Phase 4 Convergence Check (real votes, 2026-08-25)

Triggered by a Copilot review finding on PR #5286: the Round 1 table above was a synthesis, not a genuine re-vote, and ADR-073's acceptance-evidence binding requires the latter. All six agents were re-invoked in separate, isolated sessions against the current edited ADR-052 and ADR-036 text, each given their own Round 1 concerns and told to verify directly against the live repository rather than trust their prior notes. No agent had visibility into another's Round 2 output.

| Agent | Position | Key finding |
|-------|----------|-------------|
| architect | Disagree-and-Commit | All five Round 1 approval conditions verified met against live repo state. Dissent: issue #5282's existence/open state is unverifiable from this session (GitHub API returns 403); one more stale line-citation found (`detect_agent_drift.py:20-33`, quote actually at line 39) |
| critic | Disagree-and-Commit | Both P0s and all four P1s verified closed. Dissent (D-1 through D-8): the `## Decision` Option A verdict didn't cross-reference the Intentional Divergence concession; a rebutted "convergence" framing survived at one line; a Positive-consequence bullet read incoherently ("diverged... by design"); the same `detect_agent_drift.py` line-citation defect independent-thinker also found; this file's own addendum (before this edit) described a superseded intermediate fix as final; this file hadn't yet recorded Round 2 |
| independent-thinker | Disagree-and-Commit | All Phase 1 P0s verified resolved by direct artifact checks (31 templates, `build/generate_agents.py` exists, `lefthook.yml:252-276` jobs present, both workflows present, `generate_platform_agents.py` and `platform-overrides/` both confirmed absent). Dissent: #5282 unverifiable from this session; this file's Round 2 gap (now fixed by this edit); the same `detect_agent_drift.py` citation-range imprecision; standing Phase 1 dissent on "accept the direction" ambiguity, unchanged |
| security | Disagree-and-Commit | No security surface, no CWE/ASI exposure, prior two tooling weaknesses (debate-log gate substring match; `_get_adr_status` scans body not frontmatter) unworsened. New finding SEC-R2-001 (Medium): Round 1 table read as cast votes with no provenance marker, degrading the one artifact ADR-073 designates as anti-forgery evidence; fixed by this edit's relabeling |
| analyst | **Accept** | All three Phase 1 findings (stale counts, missing debate log, closed tracker) verified fixed; all six binding cross-references verified repaired by direct grep; `implemented: false` honest (`generate_platform_agents.py` confirmed absent); frontmatter reciprocity confirmed symmetric. No new issues |
| high-level-advisor | Disagree-and-Commit | Named Phase 1 block condition (any of six status-asserting lines reading bare "Accepted"/"Governing ADR") does not fire; all six verified qualified. Dissent: this file's Round 2 gap (now fixed); ADR-052's evidentiary core is preserved-as-disputed rather than resolved, which is acceptable for a reciprocity fix but should not be read as more than that; the underlying 2025-12-15 measurement is ~8 months stale, belongs in #5282's scope |

**Consensus reached**: 1 Accept, 5 Disagree-and-Commit, 0 Block. Per the adr-review protocol, this is consensus (all six agents Accept or Disagree-and-Commit). This table, not the Round 1 synthesis above, is ADR-073's acceptance evidence.

**Post-Round-2 fixes applied** (from the critic's D-1 through D-4, matching findings from architect and independent-thinker):

1. `## Decision` Option A verdict now cross-references the Intentional Divergence concession instead of standing alone on the disputed similarity metric.
2. The rebutted "projected convergence... never held" framing in the Prior Art correction paragraph was reworded to state the actual, narrower claim (no synchronization value for the layer's real purpose). **Correction (2026-08-25, Round 3 adr-review): this item is itself now superseded.** A later PR #5286 review round found the "no synchronization value" framing this fix produced was also false: `build/generate_agents.py` demonstrably synchronizes both generated agent trees today. See Round 3 below for the resulting correction (the layer's real cost is a duplicate source tree, not lost synchronization value); this item is left unrewritten as a historical record of what Round 2 actually changed, per this file's established practice of noting corrections after entries rather than rewriting them.
3. The Positive-consequences bullet claiming templates "diverged... by design" (incoherent: by-design divergence is not a defect the removal cures) was reworded to state the actual benefit.
4. The `detect_agent_drift.py:20-33` line-range citation (three agents independently found the same imprecision: the quoted text is at line 39, outside the cited range) was replaced with a docstring citation, matching the section-name convention already adopted for the ADR-036 citation.

**Not fixed, tracked instead**: issue #5282's live state is unverifiable from this session (GitHub API access is 403'd here); confirming it exists, is open, and is correctly scoped is left to whoever merges this PR, per architect's and independent-thinker's and critic's shared dissent.

## Round 3: Phase 4 Convergence Check (real votes, 2026-08-25, against post-Round-2 edits)

Triggered by a further Copilot review finding on PR #5286: four edits landed after Round 2's vote (the Decision, Prior Art, and Consequences sections were corrected to acknowledge `build/generate_agent_catalog.py` as a third live consumer of `templates/agents/`, per the correction under "Post-Round-2 fixes applied" item 2 above), so Round 2's vote did not cover the text that actually shipped. All six agents were re-invoked in separate, isolated sessions against the current edited ADR-052 and ADR-036 text, each told to verify the new claims directly against the live repository (`build/generate_agent_catalog.py`, `build/scripts/build_all.py`) rather than trust the ADR's own citations. No agent had visibility into another's Round 3 output.

| Agent | Position | Key finding |
|-------|----------|-------------|
| architect | Disagree-and-Commit | Every corrected claim verified against source; Phase 2 now sequences the catalog migration before deletion. Dissent: the consumer enumeration was still short by at least two validators (`check_skill_md_portability.py`, `check_agent_skill_discriminator.py` and its workflow); the "masks the break" framing overstated the risk since `validate_agent_catalog.py` fails loudly at pre-PR |
| critic | Disagree-and-Commit | The three-outputs/cost-not-value correction reads coherently everywhere it appears; the `build_all.py` skip-not-fail claim checks out. Dissent (D-1 through D-4): the debate log's own Round 2 "fixes applied" list still asserted the now-repudiated "no synchronization value" claim with no note; the Phase 2 "regenerates unchanged" target is unreachable (`src/claude/*.md`'s frontmatter shape differs, only 6 of 33 files carry a top-level `role:`); `generate_agents.py`'s own retirement was named in the Status section but not sequenced in Phase 2, and it exits 1 on zero shared files; the `lefthook.yml` catalog job was miscategorized as a "CI workflow" |
| independent-thinker | Disagree-and-Commit | Third consumer verified real and correctly disclosed; does not change the Claude-first cost-benefit case, only adds a migration task. Dissent: Phase 2's "regenerates unchanged" instruction is unsatisfiable by construction (frontmatter shape mismatch, hardcoded template links in the catalog renderer, LOC counts that would all change); the disclosed enforcement chain (`build_all.py` only) is narrower than the live one (`lefthook.yml`, `validate-generated-agents.yml`, and `checks_spec.py`'s hard-failing pre-PR gate) |
| security | Disagree-and-Commit | No new CWE/ASI exposure from the correction (documentation and one Migration Plan sub-step only); SEC-R2-001 verified closed. Prior tooling weaknesses (debate-log gate substring match, `_get_adr_status` scans body not frontmatter) re-verified unworsened. Dissent: the "masks the break" clause is Low-precision, since `validate_agent_catalog.py`'s exit-2 fail-closed behavior is a compensating control the ADR's phrasing omitted |
| analyst | **Accept** | All four Round 3 corrections verified true against live source directly; Migration Plan Phase 2 sequencing internally feasible; frontmatter remains reciprocal. Minor imprecision noted (the `build_all.py` skip prints a notice despite exiting 0, so "silently" slightly overstates it), not blocking |
| high-level-advisor | Disagree-and-Commit | Third consumer strengthens the record, does not change direction; a Block verdict would be dishonest signaling given the near-zero blast radius (`implemented: false`, no-deletion-on-this-authority, #5282 owns delivery). Dissent: the "3 trees to 2" consequence is an unmeasured assertion (destination `src/claude/`, ~33 files, is not a clean superset of the 31-file template source); this debate log's own Round 2 "fixes applied" list omitted the catalog correction until this edit |

**Consensus reached**: 1 Accept, 5 Disagree-and-Commit, 0 Block. Per the adr-review protocol, this is consensus. This table is ADR-073's acceptance evidence for the text as it stands after the post-Round-2 edits; Round 2 above remains the evidence for the text as it stood before them.

**Post-Round-3 fixes applied** (convergent findings from 3+ agents fixed first; single-agent findings fixed where in scope):

1. Migration Plan Phase 2 (ADR-052) rewritten: added the `generate_agents.py` retirement step (critic), corrected the "regenerates unchanged" target to acknowledge the frontmatter-shape mismatch instead of asserting an unreachable outcome (independent-thinker, critic), qualified the "masks the break" claim with `validate_agent_catalog.py`'s pre-PR fail-closed behavior (architect, analyst, security), and named the full consumer list instead of only the two CI workflows (architect, independent-thinker): `lefthook.yml`'s local job, `check_skill_md_portability.py`, `check_agent_skill_discriminator.py` and its workflow.
2. Added a Migration Plan step requiring a measured (not asserted) maintenance-surface reduction number before Phase 2 executes (high-level-advisor).
3. Annotated the Round 2 "Post-Round-2 fixes applied" item 2 above as itself superseded, per this file's established leave-the-record-append-a-note pattern (critic D-1).

**Not fixed, tracked instead**: whoever executes Phase 2 must resolve the `role:` frontmatter-shape mismatch between `templates/agents/` and `src/claude/` before the catalog generator can be repointed; this is implementation work for issue #5282, not a text fix to this ADR (independent-thinker, critic).

## Key Changes Made

1. ADR-052: added ADR-073 frontmatter (`status: accepted`, `implemented: false`, `supersedes: [ADR-036]`); rewrote `## Status` with an explicit not-yet-implemented callout naming the live pipeline and forbidding Phase 2 deletion on this authority alone; corrected stale file counts and the false present-tense CI claim in `## Confirmation`; repointed `## Implementation Status` from closed #124 to the new tracking issue; added a paragraph acknowledging ADR-036 §Intentional Divergence is not contested by this acceptance.
2. ADR-036: added ADR-073 frontmatter (`status: superseded`, `superseded-by: ADR-052`, `implemented: true`); rewrote `## Status` with a "still operative as procedure" callout naming the same live artifacts; amended `## Strategic Dependency` to note issue #124 is closed and its output (ADR-052) is now accepted.
3. Repaired six status-asserting citations to say "superseded by ADR-052, procedure still operative" instead of "Accepted", leaving content-describing citations (the synchronization procedure itself) untouched.
4. Opened issue #5282 as ADR-052's successor tracker, scoped to re-scoping and executing Phases 1-3 against the current six-surface topology.

## Recommendations to Orchestrator

**ADR-052 status**: Accepted, not implemented.
**ADR-036 status**: Superseded by ADR-052, still operative pending migration.

**Next steps**:

1. Commit both ADRs plus the six citation repairs (and regenerated Copilot skill mirrors) in this change.
2. Issue #5282 tracks the actual migration; do not execute any Migration Plan phase in this change.
3. No ADR split required.

## Artifacts Created

- `.agents/architecture/ADR-052-template-strategy.md` (amended)
- `.agents/architecture/ADR-036-two-source-agent-template-architecture.md` (amended)
- `.agents/critique/ADR-052-debate-log.md` (this file)
- Issue #5282 (migration tracking successor to closed #124)

---

## Addendum: PR #5286 review-round corrections

**Correction (2026-08-25, review): this section records fixes made during PR #5286's review, while the PR is still open, not after a merge that has not happened.** Devin Review on PR #5286 caught a stale line citation: ADR-052's Prior Art correction cited `ADR-036:45` for the "authoritative source for Claude" / "Not Generated" quote, but that text moved to line 58 once this same change added ADR-073 frontmatter to ADR-036 (a 10-line block plus blank lines, shifting every subsequent line down by 13). That fix (citing line 58) was itself superseded within the same PR: Copilot's review pointed out that a line number is the wrong fix for this class of citation, since it drifts again on the next frontmatter edit, so the final, current text cites `ADR-036 §Source 1: Claude-Specific` by section name instead, not a line number at all. The reference above to `ADR-036:45` in the Critic's Round 1 finding is left unchanged: it is a historical record of what the critic found in the pre-edit file at review time, not a live pointer, consistent with this repository's practice of leaving historical records unrewritten and noting corrections after them.

Copilot's review also caught: a wrong Copilot CLI generator output path in ADR-036 (`src/copilot-cli/*.agent.md` corrected to `src/copilot-cli/agents/*.agent.md`, the actual `outputDir` per `templates/platforms/copilot-cli.yaml`); two skill-provenance tables (`ai-agents-architecture-contract/references/provenance.md`, `ai-agents-generation-and-release/SKILL.md`) that added ADR-036/ADR-052 claims without a working re-verify probe or an updated verification date, both fixed with real probe commands (executed and confirmed) and narrowly-scoped verification dates; and `ai-agents-architecture-contract/SKILL.md`'s load-bearing-decisions table header, which still read "as of 2026-07-30" after two 2026-08-25 rows were added, reworded to note the exception. Two retrospective findings were also addressed: the two proposed learnings (dash pre-check, container clone defaults) had no owner, now tracked at issue #5288; and the Failure Mode Classification section's hedged "closest in spirit to FM #9" language was firmed into a definite classification, per `.claude/rules/retros.md` MUST 2.

Copilot's most substantive finding: this debate log's original "Final Agent Positions" table was a synthesis from Phase 1 reviews, not a genuine Phase 4 re-vote against the edited ADR text, which ADR-073 and the adr-review skill's own protocol (`debate-protocol.md:173-200`) both require before a hand-edited `status: accepted` counts as real consensus evidence. That table is now relabeled "Round 1 Positions" with its synthesized provenance stated explicitly, and the real Round 2 votes are recorded in their own section above, per Round 2's own consensus (five of six agents raised the identical relabeling requirement independently).

*Debate completed 2026-08-25*

## Addendum: overriding PR #5291's independent rejection (2026-08-25)

While this branch (`claude/autoplan-goal-1ewz33`) carried the accept decision above, a separate autonomous session on branch `claude/autoplan-goal-vd6pmg` opened PR #5291, ran its own independent 6-agent `adr-review` debate against ADR-052, and reached the opposite conclusion: `status: rejected`, 3-to-1 (high-level-advisor dissenting for `proposed`), citing zero implementation and this ADR's failure to engage ADR-036's "BY DESIGN" rebuttal of the similarity-drift evidence. The owner merged PR #5291 (2026-08-25T04:51:15Z) before this branch's PR #5286 merged, so `origin/main` briefly carried `ADR-052: status: rejected` and `ADR-036: status: accepted, superseded-by: null` before this branch's merge of `origin/main` hit the resulting conflict.

Both decisions were reached by the same debate mechanism (6-agent `adr-review`) against materially the same evidence (zero implementation, the unrebutted-similarity-metric point). The disagreement is not a factual gap either session missed; it is a genuine difference in how much weight "buildable but not yet built" carries against "accept the target and commit to building it." Put to the owner directly, with both PRs' reasoning in front of them: the owner's position was that lack of implementation is not on its own a reason to reject a proposal that is buildable, and reaffirmed the accept decision. This merge keeps `status: accepted`, `supersedes: [ADR-036]`; PR #5291's rejected text does not survive the merge. Issue #5282, already open as this acceptance's implementation-tracking successor to #124, is the real commitment the owner's reaffirmation implies: the Migration Plan is not meant to sit unimplemented indefinitely.

This is recorded here rather than silently overwritten because PR #5291's rejection was not a rubber-stamp either: it carried its own real 6-agent debate, its own dissent, and correct evidence. A future reader diffing `origin/main`'s history will see `status` flip `accepted -> rejected -> accepted` within roughly three hours, both changes debate-backed, both merged by the owner. That is not thrashing to be embarrassed about; it is two independent evaluations of the same buildable-but-unbuilt tension, resolved by the one authority who can resolve it directly.
