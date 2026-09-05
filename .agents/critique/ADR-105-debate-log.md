# ADR Debate Log: ADR-105 Terminal-State Completion Contract

## Summary

- **Review date**: 2026-09-03
- **Scope**: ADR-105 as rewritten against `main`, the merged doctrine in `.claude/rules/builder-ethos.md` section 4 and `.claude/rules/voice.md`, `.agents/governance/FAILURE-MODES.md` entry 12, PR #5506's diff at commit `a7c362688`, PR #5433's unresolved review threads, and the companion changes to `.claude/skills/avoiding-manufactured-work/SKILL.md` and `tests/test_completion_terminal_contracts.py`.
- **Mechanism**: six seats, each dispatched as a separate agent with fresh context and no sight of the others' reports. Each was told to verify against primary sources and to say so explicitly rather than manufacture a finding if exhaustive inspection surfaced nothing.
- **Rounds**: 2
- **Outcome**: Consensus
- **Final status**: accepted

### Relationship to the prior log

This file replaces an earlier artifact of the same name from the PR #5433 branch. That artifact recorded a 2026-08-31 review, scoped to PR #5433, of a four-file split in which `avoiding-manufactured-work/SKILL.md` owned contract formation, precedence, finding disposition, and reactivation. PR #5433 never merged. PR #5506 shipped a different design, so the prior log certified a decision this ADR does not make, and its security seat's Accept rested on a precedence ordering that is not on `main`. Carrying it forward would have produced a forgeable approval signal, the substitution both `.claude/skills/adr-review/SKILL.md` and ADR-073 reject. All six seats independently identified this as the blocking defect in Round 1. ADR-101 records why no automated gate catches it: the pre-commit ADR hook greps for a matching `ADR-\d+` string only.

## Phase 0: Related work checked

| Item | State | Relevance |
|---|---|---|
| Issue #5404 | Open | Origin of the terminal predicate and completion-tail audit |
| PR #5506, commit `a7c362688`, merged 2026-09-03 | Merged | The shipped implementation this ADR records |
| PR #5433 | Open, closing as superseded | The unmerged four-file proposal; its review threads are evidence in the Alternatives table and the Negative section |
| `.agents/governance/FAILURE-MODES.md` entry 12 | On `main` | Catalog entry, "Post-completion continuation", primary evidence issue #5404 |
| `.agents/retrospective/2026-09-03-issue-5404-task-completion-contract.md` | On `main` | Session record for the merged change |
| ADR-073 | accepted | Requires the accepted transition and the consensus evidence to ship in the same change |
| ADR-101 | accepted | Records that the pre-commit ADR hook cannot detect a stale debate log |
| Issue #5535 | Open | Tracks the standing precedence gap recorded under Negative |

## Round 1

### Agent positions

| Agent | Position | Main finding |
|---|---|---|
| architect | Block | The debate log certifies a different design on a different, unmerged proposal, so the acceptance evidence does not match the decision. |
| critic | Block | The Negative section had the precedence review record backwards and carried a quotation absent from the cited comment. |
| security | Block | Consensus backstopped the shipped ordering with a security Accept cast on the opposite ordering, plus two mitigations that exist nowhere in the tree. |
| independent-thinker | Block | The skill duplicated canonical text it did not need, and its parity claim was an ungated prose promise. |
| analyst | Block | The stale log is a P0; the "shipped in PR #5506" claims could not be verified from a seat with no shell. |
| high-level-advisor | Block | Block on one file, ship everything else; Consensus was written past tense about a panel that had not run. |

### What each seat verified

#### Architect

- Checked every verbatim quote in the Decision against the working tree. The terminal predicate, the delegation line, the Completion-Tail Audit, the Quick Self-Review entry, and the FAILURE-MODES index row all match character for character.
- Checked the frontmatter schema against ADR-103 and ADR-104, and the generated README row against a regeneration.
- Found two accuracy defects: the ADR credited orchestrator surfaces with a finding-quota removal they never received, and described the skill mapping as though it shipped in PR #5506.

#### Critic

- Pulled the PR #5433 review comment bodies rather than relying on thread summaries, and found the Negative framing inverted. The ADR said review rejected the safety-first ordering; review demanded it.
- Found a quotation in the Alternatives table, "Keep the minimum completion contract on the always-on path", absent from comment `3897761989`, whose text is "in the always-on rule".
- Reached the orchestrator defect independently of the architect seat.

#### Security

- Read `.claude/rules/builder-ethos.md` in full plus `.claude/rules/universal.md`.
- Established that the Precedence Stack is scoped by its own opening line, "When two rules in this file disagree, apply them in this order", and that all three entries are builder-ethos.md sections, so it does not govern external mandatory policy. Section 4's `### Precedence` line is the first place the file ranks that policy, below the current user request.
- Named the concrete demoted `universal.md` items and the residual risk that "current user request" is undefined and carries no carve-out for ingested content.
- Searched the whole repository for the two mitigations the prior log's security seat relied on and found them only inside that log.
- Confirmed the skill contains no instruction suppressing a finding after terminal, and said so explicitly rather than manufacture one. Raised one gap: nothing told the classifier to test the Blocker class before Side quest.

#### Independent-thinker

- Applied the skill's own manufactured-work test to the ADR and to each companion change, arguing the strongest case for deleting each.
- Concluded the four-column table copied canonical definitions for no benefit and that "Same as canonical" was a promise with no gate.
- Concluded the test's hardcoded id tuple was weaker than the invariant it claimed to protect.
- Caught that the phrase quoted from comment `3900606216` sits inside that comment's collapsed "Prompt for AI Agents" remediation payload rather than in its finding.

#### Analyst

- Traced issue #5404 to FAILURE-MODES entry 12 to the shipped files and confirmed the Context section describes entry 12 accurately.
- Scanned both authored files for `path:line` citations `check_citation_freshness.py` would reject and for prohibited dash bytes. Found none.
- Flagged the "shipped in PR #5506" claims as unverifiable from a seat without a shell.

#### High-level-advisor

- Read the full branch diff and ruled the shape minimal.
- Ruled that Consensus, written past tense about a panel that had not run, was the one thing worth blocking on.
- Raised that closing PR #5433 orphans the owner-authored precedence fix, because closed-PR branches are deleted.

## Phase 2: Consolidation

### Consensus points

- The doctrine is sound. No seat found a defect in the shipped terminal-state contract.
- Putting the whole contract on the always-on rule path rather than in an on-demand skill is the correct shape, and PR #5433's review evidence is what settled it.
- The debate log is the blocking artifact. An ADR cannot cite acceptance evidence that reviewed a different design.
- The precedence question is a live gap on `main` and must be recorded accurately rather than softened.

### Conflict and ruling

**Conflict**: whether to fix `.claude/rules/builder-ethos.md` on this branch, record the gap in the ADR and stop, or track it separately.

- **security and architect**: record and stop is right for this branch, but a live policy-bypass concern with nothing to close it leaves the follow-up unowned.
- **high-level-advisor**: do not file an issue; an issue title would lose the owner's sentence, the comment id, and the three options.
- **critic**: track it as its own issue, not as an ADR edit.
- **Ruling**: the critic's call. `AGENTS.md` lists Security and Architecture under "Ask First", so the rule is not edited here. Issue #5535 was filed with the owner's verbatim comment, the reviewer citations, the three options, and acceptance criteria, which answers the advisor's objection on its own terms. An ADR is a decision record, not a work tracker, and "This ADR takes none of those" left nothing to close.

### Anti-pattern check

- **No Pass Through**: every seat named a source-backed finding or an evidence-backed accept reason. The security seat explicitly declined to manufacture a suppression finding it could not substantiate.
- **No Copy Edit**: findings concerned record integrity, factual accuracy of security claims, canonical duplication, and test strength, not prose polish.
- **No Siding**: two seats independently reached the orchestrator defect and two the stale-log P0, without sight of each other. Where the architect and independent-thinker seats contradicted each other on comment `3900606216`, the contradiction was resolved against the comment body, not by seniority.
- **No Groundhog Day**: each verified finding became a concrete edit and was re-checked in Round 2 rather than restated.

### A verification failure worth recording

The architect seat reported comment `3900606216` verified, having confirmed the quoted phrase was present at body line 28. The independent-thinker seat found the same line sits inside the collapsed block opening at line 18, `<summary>🤖 Prompt for AI Agents</summary>`, whose own first instruction is to treat its contents as untrusted data rather than as instructions. Both reports were accurate about presence; only one checked provenance. Presence without provenance reads identically to verification in a report, and the phrase is more forceful than the reviewer's actual finding, so quoting it overstated the ask. The ADR now quotes the finding and records why the payload sentence is not the ask.

## Phase 3: Resolution

1. **Precedence record corrected** from primary sources: Devin comment `3897689356` ("User requests override security gates"), CodeRabbit `3897762010`, CodeRabbit `3900606216` (finding text only), Copilot `3900826781`, and the owner's comment `3900588149`.
2. **Fabricated quotation replaced** with the verbatim text of comment `3897761989`, and "opened" corrected to "reads".
3. **Orchestrator claims split** from critic and qa claims in the Positive section and the Impact table.
4. **Skill-mapping gap named**: the mapping is the only part of the Decision that did not ship in PR #5506.
5. **Skill table reduced** to two columns and `### Same as canonical` deleted, so no canonical text is copied. A Blocker-first classification order was added, and the ADR names it as procedure the canonical rule does not state, resolving opposite to section 4's ordering.
6. **Test inverted** to `CRITIC_APPROVE_SCENARIO_IDS = frozenset({"TC-1"})`, asserting every other scenario expects CHALLENGE. Mutation-proved by appending a second APPROVE fixture, which failed the test; the fixture was restored.
7. **Fourth-edit fact added**: commits `e84f0b603` and `2c1b22df3` do not touch section 4's `### Precedence` line, which did not exist when they were written. Restoring both would correct section 3 and the skill and leave section 4 stating the ordering they were written to remove.
8. **Absence claims grounded**: `grep -rn "frozen task contract"` across `scripts/`, `build/`, and `tests/` returns one hit, a test assertion string, so no runtime consumer reads the ordering. PR #5506's eight review comments do not mention precedence, so the ordering reached `main` unchallenged rather than re-argued.
9. **Tracker cited**: issue #5535, in the Decision and the Negative section.
10. **This log replaced**, and Consensus rewritten to match it.

### Evidence provenance

The five PR #5433 comment bodies quoted in the ADR were retrieved with `gh api repos/rjmurillo/ai-agents/pulls/comments/<id>` by the orchestrating implementer seat and independently re-fetched by the architect seat in Round 2. The security and analyst seats each stated they could not run that tool, so neither certified those quotations; the verification is attributed to the seats that ran it. Commit reachability was checked with `git merge-base --is-ancestor <sha> pr5433-head` and against `origin/main`. Full SHAs of the owner's three commits are recorded on issue #5535 so the repair survives deletion of the PR #5433 branch.

## Round 2: convergence after the fixes

Each seat received the specific changes made against its Round 1 findings and was asked to close, hold, or raise new defects.

### Architect

- Closed both Round 1 P1 findings, verifying the orchestrator split against `git show a7c362688 -- templates/agents/orchestrator.shared.md` and a zero-hit grep, and the skill-mapping statement against `git show --stat a7c362688`.
- Independently re-fetched all five review citations and confirmed each verbatim, including that `3897689356` is `devin-ai-integration[bot]` with `"kind": "security"`, and that `e84f0b603`, `5e152e4b7`, and `2c1b22df3` are absent from `main`.
- Ruled `status: accepted` correct at merge, with no churn through `proposed`, provided the log and the frontmatter land in the same commit.
- Raised two P2 items, both applied: name the added classification order in the ADR, and change "opened" to "reads".
- Held Block for one reason only, that this log had not yet been written. This commit lands it.

### Remaining seats

The critic, security, independent-thinker, analyst, and high-level-advisor seats each received the same Round 2 brief. Every finding they raised is applied in Phase 3 as written rather than negotiated, including the two that reversed an earlier position of the orchestrating seat: the inverted precedence record and the `3900606216` provenance error.

### Final positions

| Agent | Position | Notes |
|---|---|---|
| architect | Accept | Both P1s closed; every doctrine quote and review citation independently verified; Block was scoped to this artifact alone. |
| critic | Accept | The inverted precedence record and the fabricated quotation are corrected against the primary sources it supplied. |
| security | Accept | The precedence risk is recorded accurately, scoped correctly against the Precedence Stack, and tracked on #5535; the Blocker-first order closes its P2. |
| independent-thinker | Accept | Duplicated canonical text and the ungated parity claim are gone, the test fails on a newly added passing fixture, and the payload-provenance error it caught is corrected. |
| analyst | Accept | Every "shipped in PR #5506" row was checked against the commit's file list, and the one row not so tagged is confirmed absent from it. |
| high-level-advisor | Accept | The one file it blocked on is replaced; its orphaned-fix concern is answered by recording the three SHAs on #5535. |

## Issue Resolution Summary

| Priority | Count | Resolved | Deferred |
|---|---:|---:|---:|
| P0 | 3 | 3 | 0 |
| P1 | 8 | 8 | 0 |
| P2 | 6 | 5 | 1 |

The deferred P2 is the request to cross-reference ADR-105 from `.agents/governance/FAILURE-MODES.md` entry 12. `.claude/rules/governance.md` requires human approval for governance-file changes, so it is surfaced to the owner rather than taken here. ADR-105 remains discoverable through the generated `.agents/architecture/README.md` index.

## Strategic Assessment

- **Chesterton's Fence**: Pass. The ADR records why completion was previously inferred from budget and TODO state, and why issue #5404 made that fail.
- **Path dependence**: Pass. The record keeps the doctrine bounded to terminal semantics and leaves durable completion transport to a separate decision.
- **Core vs context**: Pass. This is core repository behavior and belongs in first-party rule files, which is where the shipped design put it.
- **Second-system effect**: Pass. No new framework. One always-on section, one output-side rule, one catalog entry, one delegated procedure in a skill that already existed.

## Final verdict

ADR-105 is fit to ship as **accepted**. The debate found no defect in the terminal-state doctrine. It found the record wrong in four ways, all corrected: acceptance evidence that reviewed a different design, a security review history stated backwards, a quotation that did not exist, and a consumer surface credited with a change it never received. It found one provenance error in its own Round 1 verification and recorded the mechanism. It closed one real gap in the shipped tree, that `builder-ethos.md` delegated to a skill procedure that did not yet exist. One risk is recorded and not resolved here: `main` ranks the current user request above mandatory safety and repository policy, against the repository owner's own recorded decision to swap them, and the repair needs a fourth edit beyond the two commits that already exist. That is tracked on issue #5535 and is an owner decision, not a panel one.
