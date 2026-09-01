# ADR Debate Log: ADR-105 Terminal-State Completion Contract

## Summary

- **Review date**: 2026-08-31
- **Scope**: ADR-105, issue #5404, PR #5433, and the live doctrine text in `.claude/rules/builder-ethos.md`, `.claude/rules/voice.md`, `.claude/skills/avoiding-manufactured-work/SKILL.md`, and `.agents/governance/FAILURE-MODES.md` #12.
- **Mechanism**: One orchestrated session ran the six `adr-review` seats as separate evidence-first passes. No subprocess agents were spawned. Each retained claim was rechecked against a primary source before it was kept.
- **Rounds**: 2
- **Outcome**: Consensus
- **Final status**: accepted

## Phase 0: Related work checked

| Item | State | Relevance |
|---|---|---|
| Issue #5404, "Add terminal-state invariant to stop completed agent runs" | Open | Source of the terminal predicate, completion-tail audit, precedence block, and the zero-finding review scenario the PR also ships |
| PR #5433 | Open | Implements the doctrine, carries the Devin security finding on precedence order, and carries Copilot's review demand for a real six-seat debate log |
| `.agents/governance/FAILURE-MODES.md` #12 | Modified in this PR | Canonical failure-mode catalog entry that points back to the four doctrine owners and to ADR-105 |
| ADR-073 | accepted | Makes frontmatter authoritative and requires accepted-state evidence to ship with the same change as the debate log |
| `.claude/rules/governance.md` | Active rule | Rule 3 and rule 5 reject the specialist-only substitute that ADR-105's original Consensus section tried to rely on |
| ADR-104, ADR-102, ADR-100/101 debate logs | Existing prior art | Established the repo's current debate-log format, depth, and the standard of naming both process gaps and content corrections |

## Round 1

### Agent positions

| Agent | Position | Main finding |
|---|---|---|
| architect | Disagree-and-Commit | The four-file ownership split is structurally sound, but the Consensus section still claims a reduced-scope exception that no canonical governance file defines. |
| critic | Block | The decision can ship, but the record cannot: accepted-state evidence was still missing, and the ADR still said the panel had not run after the panel had run. |
| independent-thinker | Block | "Prose-only" did not make this small. `builder-ethos.md` and `voice.md` are always-on rule files loaded by every role, so the narrowed-blast-radius rationale had to be deleted, not defended. |
| security | Accept | The precedence-order deviation from issue #5404 closes a live bypass path and is now consistent across the skill and `builder-ethos.md` section 3. |
| analyst | Disagree-and-Commit | The evidence chain issue #5404 -> FAILURE-MODES #12 -> the four doctrine files is intact. The missing link was the debate artifact this review was creating. |
| high-level-advisor | Block | The only thing keeping `status: proposed` in place was the absent debate artifact. Once the artifact exists, the record should say so plainly and move to accepted. |

### What each seat verified

#### Architect

- Verified the ownership split against the live files. `builder-ethos.md` section 4 owns the terminal predicate, `voice.md` owns the Completion-Tail Audit, `avoiding-manufactured-work/SKILL.md` owns contract formation, precedence, finding disposition, and reactivation, and FAILURE-MODES #12 cross-links the whole doctrine.
- Checked ADR-073's frontmatter contract. `status: proposed` was correct before debate evidence existed, and it had to remain so until the debate log landed in the same change.
- Flagged one P1 record defect: the ADR's own Consensus section still said the six-seat panel did not run and treated a scoped substitute as compliant. `.claude/rules/governance.md` does not define that escape hatch.

#### Critic

- Re-ran the fresh-reviewer objection Copilot raised on PR #5433. The comment was right: the old Consensus section contradicted `.claude/rules/governance.md` and the `adr-review` skill's accepted-transition gate.
- Checked the rest of the ADR for real holes. Alternatives, risks, and the precedence-order deviation were all stated with enough detail to review. The blocker was record integrity, not the decision itself.
- Flagged one more P1 accuracy gap: the ADR's Neutral and Impact sections still described critic/qa consumer updates and mirror sync as future or optional follow-up, but PR #5433 already ships those changes.

#### Independent-thinker

- Challenged the claim that this was narrower than ADR-099, ADR-100, or ADR-101 because it was "prose-only". The always-on files here steer every role on every turn. That is repo-wide behavior change, even without a schema or CI gate.
- Tested the strongest contrarian reading: if the reduced-scope rationale falls, does the decision itself fall with it? No. The right correction is to run the full panel and delete the rationale, not to reject the terminal-state contract.
- Agreed the four-file ownership split itself is the simpler shape. A two-file design would have forced `builder-ethos.md` or `voice.md` to duplicate the skill's operational mechanics.

#### Security

- Verified the exact issue text. Issue #5404's literal precedence block put `explicit current user request` above `mandatory safety and repository policy`.
- Verified the live fix. `avoiding-manufactured-work/SKILL.md` now orders `mandatory safety and repository policy` above `explicit current user request`, and `builder-ethos.md` section 3 now says User Sovereignty stops short of a mandatory safety or repository-policy blocker.
- Re-checked the ADR's named highest-risk item against the shipped text and the PR review comments. Devin's security finding remains valid on the old issue ordering and resolved on the shipped ordering. No new security blocker remained.

#### Analyst

- Verified the source chain in both directions. Issue #5404 names the terminal predicate, completion-tail audit, precedence, reactivation, and zero-finding review case. FAILURE-MODES #12 now points to the same four doctrine owners and names the runtime-proof deferral honestly.
- Verified the Copilot review comment's premise. `.claude/rules/governance.md` and `.claude/skills/adr-review/SKILL.md` do not define a blast-radius exception to the six-seat panel requirement for cross-role policy changes.
- Checked whether the PR's extra reviewer-surface edits broke the ADR's four-file focus. They did not. They are downstream consumers of the doctrine, not competing canonical owners, but the ADR still needed to stop describing them as future work once the PR had already shipped them.

#### High-level-advisor

- Asked the only question that changes ship/no-ship timing: does any unresolved content risk justify keeping the ADR proposed after the required panel has now run? Answer: no.
- Ruled that the decision is already the minimum useful shape. Splitting the doctrine further would add sources of truth. Holding acceptance for a second process round would add delay with no new evidence.
- Directed Phase 3 to fix the record, not the doctrine: replace the obsolete reduced-scope justification with the actual panel result, then accept.

## Phase 2: Consolidation

### Consensus points

- The terminal-state doctrine itself is sound. No seat found a P0 in the four-file ownership model.
- The precedence-order deviation from issue #5404's literal text is justified and safer than the issue's original ordering.
- ADR-073's accepted-transition rule is load-bearing here: debate evidence must ship with the same change as the `status: accepted` transition.
- The old reduced-scope-consensus rationale is no longer defensible once the real panel has run.

### Conflict and ruling

**Conflict**: whether the ADR needed content edits beyond the Consensus section.

- **critic**: yes, because the Neutral and Impact sections still described critic/qa consumer updates and mirror sync as future or optional follow-up.
- **architect and analyst**: yes, but narrowly. The four-file ownership split stays. Only the stale record of what this PR already ships needs correction.
- **high-level-advisor ruling**: the narrower view prevails. Keep the decision centered on four canonical owners, but update the ADR so its Neutral and Impact sections match the shipped consumer and mirror follow-through.

### Anti-pattern check

- **No Pass Through**: every seat named a source-backed finding or an evidence-backed accept reason.
- **No Copy Edit**: findings were about governance contract, precedence safety, scope claims, and evidence, not prose polish.
- **No Siding/Dead End**: each seat stayed on ADR-105, issue #5404, or the files the ADR names.
- **No Groundhog Day**: the Copilot and Devin findings were verified once, then converted into concrete record fixes rather than repeated as slogans.

## Phase 3: Resolution

Two P1 record defects were fixed in the ADR.

1. **Consensus basis corrected.** Replaced the old reduced-scope narrative with the actual six-seat review outcome and the debate-log path.
2. **Shipped follow-through recorded accurately.** Updated the Neutral and Impact sections to say what PR #5433 already does: regenerate the rule mirrors and update the critic/qa consumer surfaces and clean-review eval guard.

No change to `.claude/rules/builder-ethos.md`, `.claude/rules/voice.md`, their generated mirrors, or the skill text was required by the debate itself. Security rechecked the shipped precedence qualifier and found it internally consistent.

## Round 2: convergence after record fixes

### Changes made

- Added `.agents/critique/ADR-105-debate-log.md`.
- Rewrote `ADR-105`'s `## Consensus` section to record the actual panel result.
- Updated `ADR-105`'s Neutral and Impact sections to reflect the critic/qa consumer updates and regenerated mirrors already present in PR #5433.
- Flipped ADR-105 frontmatter from `status: proposed` to `status: accepted` in the same change as this debate log.
- Regenerated `.agents/architecture/README.md` so the index matches the accepted frontmatter state.

### Final votes

| Agent | Position | Notes |
|---|---|---|
| architect | Accept | Ownership split, frontmatter state, and acceptance evidence now align. |
| critic | Accept | Record integrity defect closed. No unresolved P0 or P1 remains. |
| independent-thinker | Accept | The full panel ran, and the unsupported reduced-scope claim is gone. |
| security | Accept | Precedence-order safeguard stands. No policy-bypass hole remains in the doctrine record. |
| analyst | Accept | Issue, ADR, failure-mode catalog, and shipped file set now tell the same story. |
| high-level-advisor | Accept | Fit to ship now. Further delay would be process theater. |

Final tally: **6 Accept, 0 Disagree-and-Commit, 0 Block**. Consensus reached.

## Issue Resolution Summary

| Priority | Count | Resolved | Deferred |
|---|---:|---:|---:|
| P0 | 0 | 0 | 0 |
| P1 | 2 | 2 | 0 |
| P2 | 0 | 0 | 0 |

## Strategic Assessment

- **Chesterton's Fence**: Pass. The ADR still records why the old behavior existed and why issue #5404 made it fail.
- **Path dependence**: Pass. The record keeps the live doctrine bounded to terminal semantics and leaves runtime proof to the named follow-up.
- **Core vs context**: Pass. This is core repo behavior. It belongs in first-party rule and skill files, not in a bolt-on helper.
- **Second-system effect**: Pass. The chosen fix adds no new framework. It reuses existing rule and skill seams.

## Final verdict

ADR-105 is fit to ship as **accepted**. The debate found no defect in the terminal-state doctrine itself. It found two record defects, both now fixed: the missing panel evidence, and the stale description of what the PR already ships.
