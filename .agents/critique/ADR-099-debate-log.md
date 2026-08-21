# ADR-099 Debate Log

**Subject**: `.agents/architecture/ADR-099-session-qa-binding-field-precedence.md`, addressing issue #5217.

**Round**: 1 of up to 10 (per adr-review debate protocol).

## How this review was conducted, and what that costs

Read this section before weighing anything below it.

The `adr-review` protocol calls for six independent agents (architect, critic, independent-thinker, security, analyst, high-level-advisor). **No independent agent processes ran.** The harness serving this session registers no subagent-spawn tool: `Task` and `Agent` are absent from the tool set, and a `ToolSearch` for delegation returned only `TaskStop`, `SendMessage`, `EnterWorktree`, and the GitHub Copilot coding-agent delegator, none of which spawn a reviewing agent against a local file. The available cross-session mechanism (`create_session`) spawns siblings into this same environment and working tree, on a branch this session is instructed not to disturb, which is a worse risk than the one it would mitigate.

What ran instead: one session applied the six review lenses as six separate passes, each writing findings before the next began, and each finding was either verified against the repository or dropped. That is a single-reviewer review. The `adr-review` skill names "Single-agent ADR review" as a process anti-pattern, and this log does not claim otherwise.

The gate this log satisfies is structural. `check_adr_review_policy` (`scripts/validation/git_hook_policy.py:1382-1417`) requires a staged debate log under `.agents/critique/` whose content references the staged ADR's ID. It does not and cannot verify that six agents ran. A log asserting a 6/6 agent tally here would pass the same gate and would be a fabricated approval signal, which is the failure mode the skill's own acceptance checklist names ("a forgeable approval signal"). So the tally below is recorded as lens-by-lens findings, not as votes.

**What a maintainer should do with this.** The findings are verified and the ADR is stronger for them. The independence the protocol buys is missing. Re-running the real six-agent debate on a harness that has the tooling is cheap relative to the change, and is the recommended path before this ADR is treated as having cleared the multi-agent bar. That recommendation is repeated in the implementing PR.

## Findings by lens

Every finding below names the check that confirmed or refuted it. Findings that did not survive verification are recorded as refuted rather than deleted.

### Analyst (evidence, feasibility)

- **P1, confirmed and fixed.** The draft cited the mirror generator as `copy_lib_to_platform`, a name carried in from the task framing. No such function exists. `grep -rn "copy_lib_to_platform" build/scripts/` returns nothing; the generator is `_build_lib` (`build/scripts/build_all.py:316-335`), which delegates to `_build_directory_copy` and mirrors the whole of `.claude/lib/`. Corrected in the Impact table. This is exactly the citation class `.claude/rules/canonical-source-mirror.md` exists for: the claim read as verified because it was specific.
- **P1, confirmed.** No `sync_plugin_lib.py` involvement. `SYNC_PAIRS` (`scripts/sync_plugin_lib.py:27-31`) names three package directories and `SYNC_FILE_PAIRS` (`:41-47`) names two files; `qa_report.py` is in neither. The ADR now cites both line ranges rather than asserting the absence.
- **P1, confirmed.** `.claude/skills/session-end/scripts/complete_session_log.py`, which ADR-096 named as a second caller on 2026-08-19, does not exist at `9e1ebd2b8`. `find . -name complete_session_log.py` returns nothing and `.claude/skills/session-end/` is absent. `grep -rn session_qa_binding` finds one production caller (`scripts/validate_session_json.py:963`), one mirror definition, and eight test call sites.
- **P1, confirmed.** The claim that `validate_qa_report()` never reads `expected.commit` is checkable and checked: the function body (`.claude/lib/qa_report.py:199-209`) references `expected.session_log` once and `expected.commit` never. This is load-bearing for the whole argument, because it is what makes the binding commit a fallback rather than the compared value.
- **P2, noted.** The 50-commit shallow clone blocks any ancestry or ordering claim about the two SHAs in the one disagreeing log, and blocks recovering the check's introducing commit. Both limits are annotated in the ADR rather than worked around, matching ADR-096's handling of the same limit.

### Critic (gaps, risks, completeness)

- **P0 candidate, verified and resolved.** The ADR's central promise is that the disagreement becomes non-blocking. If `result.warnings` fed any strict mode or exit path, that promise would be false and the change would swap one hard failure for another. Verified: `scripts/validation/models.py:20-21` states "A result with no errors is valid. Warnings do not affect validity," and `main()` returns `0 if result.is_valid else 1`. The ADR now quotes the invariant instead of asserting it. Had this gone the other way it would have invalidated the design, not merely the prose.
- **P1, refuted.** Concern that adding a field to `QaBinding` breaks the seven untouched test call sites that compare against a two-argument construction. It does not: the field is last and defaults to `None`, so both constructions produce equal instances. Recorded in the Impact table as an explicit no-change row rather than left silent.
- **P1, confirmed and fixed.** `.claude/rules/ci-scripts.md` MUST 13 governs a PR that introduces a gate. This PR removes one and adds a warning, so MUST 13 does not bind. The ADR previously left this to inference; it now says so and offers the corpus figure as a blast-radius measurement rather than as MUST-13 compliance. Claiming compliance with a rule that does not apply is its own defect.
- **P2, confirmed and fixed.** Acceptance criteria named a wiring test but the Implementation Notes did not. `.claude/rules/testing.md` SHOULD 6 wants a test that drives the consumer's real entry point, because a unit test on `session_qa_binding()` cannot observe whether `validate_qa_report_evidence()` ever reaches `result.warnings`. Now named in both places.

### Independent-thinker (challenge the assumptions)

- **P1, confirmed and fixed. The strongest finding in this review.** The ADR's argument leans on the schema's statement that QA rebinding advances `comparison.head`, and then treats `comparison.head` as the safely-newer field. That is only one of two drift directions. `.claude/rules/session-logs.md` MUST 2 and MUST 3 advance `endingCommit` independently, so a log extracted before its follow-up commit carries `endingCommit` newer than `comparison.head`, and selecting `comparison.head` there selects the *older* SHA and therefore the shorter, laxer staleness range. The draft did not state this and would have shipped with its central justification covering half the cases.
  Verified rebuttal, now in the ADR as its own section: the laxer direction cannot fail open, because `post_qa_code_changes()` runs `git merge-base --is-ancestor report.commit head` first (`.claude/lib/qa_report.py:230-242`) and raises on return code 1. A report validated later than the selected head is precisely the non-ancestor case. The design survives the objection; the draft's reasoning did not, and the difference is what this pass was for.
- **P1, confirmed and fixed.** The corpus measurement (1 disagreement in 1458 logs) reads as evidence the problem is negligible, and taken alone it argues against the change. It undercounts by construction: the rebind loop's whole nature is editing a disagreeing log into agreement *before* committing it, so every closed loop is filed under the 34 agreeing logs. The ADR now states the 1 is a floor rather than an estimate, and points at the handoff's 23 mentions across 15 rounds for the cost-per-occurrence. Presenting the corpus figure without this caveat would have been the more dishonest option, since the figure superficially favors the conclusion the ADR argues against.
- **P2, considered and rejected.** Whether the `inconsistency` field is over-engineering versus a bare deletion of the raise. Kept: seven lines against the loss of the only signal on `comparison.head`, and `.claude/rules/ci-scripts.md` SHOULD 4 treats a repair to a silent failure as itself a silent-failure candidate.

### Security (threat model)

- **Confirmed, no new capability.** The relaxation does not widen what an attacker can do. Both fields live in one self-attested file authored by the same actor the check judges, so defeating the equality check has always cost one extra edit. ADR-096 recorded this trust model for the QA report; it applies more strongly to two fields of the same document. Nothing here is an adversarial control before or after.
- **Confirmed, fail-closed preserved.** The ancestry check in `post_qa_code_changes()` is the real containment and is untouched. See the independent-thinker finding above for the case that depends on it.
- **P2, confirmed and fixed.** Both SHAs are interpolated into a warning string that reaches operator output. Verified that neither can carry arbitrary session-log content: `comparison_head` passes `_FULL_COMMIT_PATTERN.fullmatch` at `:170-172` before the branch is entered, and `resolved_ending` is assigned only under the same pattern on both paths (`:158-159`, `:167-168`). Stated in the ADR rather than left for a reader to re-derive.
- **Noted, out of scope.** The `QA_EVIDENCE_PREFIXES` boundary gaps that ADR-096's security review raised (instruction-prose coverage, the self-referential `.agents/qa/` entry, `AI_AGENTS_ARTIFACT_ROOT` desync) are untouched here and remain a separate follow-up. This ADR does not widen that surface.

### Architect (structure, governance, coherence)

- **P2, confirmed and fixed.** `QaBinding`'s docstring reads "Session and commit identity that QA evidence must match." The new field is not identity; it is an observation about how identity was selected. Implementation Notes now require the docstring to change in the same edit, so the class does not silently acquire a second responsibility.
- **P2, confirmed and fixed.** An abbreviated `comparison.head` (the schema permits 7 to 40 characters) is invisible to this function: `:170-172` tests the full-SHA pattern and falls through, with none of the `resolve_commit` handling `endingCommit` gets at `:160-168`. Pre-existing and untouched, but it is load-bearing for the corpus figure, since it is part of why 1417 of 1458 logs never reach the check. Now recorded as a named residual instead of an unexplained gap in the measurement.
- **Confirmed.** Template conformance against `.agents/architecture/ADR-TEMPLATE.md`, frontmatter enum (`status: proposed`, `implemented: false`, `superseded-by: null`, `explainer: null`), and number uniqueness (`check_adr_uniqueness.py` reports all unique, next free 100).
- **Confirmed.** Scope holds. The ADR touches one function and one caller and declines to widen into `QA_EVIDENCE_PREFIXES` or the schema.

### High-level-advisor (priority, proportionality)

- The change is proportionate: one raise deleted, one field added, one warning wired, on a P2 issue with a documented interactive cost. It does not attempt the second-system rewrite an ADR in this area could easily become.
- The alternatives table carries a real recommendation with real trade-offs and rejects the issue's own suggested direction on stated grounds, which is what the issue asked for. Rejecting a suggestion from the issue author is the correct output when the analysis supports it, and the ADR gives three specific reasons rather than a preference.
- Sequencing is correct: ADR accepted before code, per `.claude/rules/ci-scripts.md` MUST-NOT-2, which is the gate ADR-096 failed on its own first two heads.
- The one open risk is process, not design: the missing agent independence recorded at the top of this log.

## Resolution

Seven findings were applied to the ADR in place. Two of them (the drift-direction gap and the corpus undercount) changed the argument rather than the prose, and one (the `copy_lib_to_platform` citation) corrected a claim that was specific and wrong. No finding challenged the decision itself, and the design survived the one objection that could have unseated it.

## Outcome

**The ADR is considered implementation-ready on its technical merits, with a recorded process gap.** The six lenses were applied and their findings resolved; the six independent agents were not available and did not run. That gap is disclosed here and in the implementing PR rather than papered over with a tally. A maintainer who wants the multi-agent bar met should re-run `adr-review` on a harness with subagent tooling before treating this ADR as having cleared it.

The frontmatter `status` transitions to `accepted` in the same change as this log, per ADR-073's Phase-3 acceptance gate and the precedent ADR-096 set after failing it twice.

## Round 2 (post-implementation, evidence that became available after the review)

The pre-push `push-ref-policy` hook refused the branch because the clone was shallow and told the session to run `git fetch --unshallow origin`. Doing so made three claims checkable that Round 1 had recorded as undeterminable, and two of them were stale as written. Corrected in the same change as this entry.

- **"When introduced: not determinable from this checkout" is now determinable, and was wrong to leave open.** `226bef0e4`, 2026-08-08, PR #4735, "fix(memory): replace #4707 duplicate path validator", is the file's only `--diff-filter=A` commit and the only hit for `git log -S "comparison head and endingCommit resolve to"`. The module arrived whole at 252 lines with the check already in it, inside a PR about something else. That converts the Historical Rationale's "no alternatives recorded at introduction" from an absence claim into an evidenced one, which `.claude/rules/knowledge-persistence.md` MUST NOT 4 asks for: an absence asserted from a single probe is the weaker form, and this one now cites the search that establishes it.
- **The two SHAs in the one disagreeing log do not resolve, and clone depth was the wrong explanation.** With 2613 commits fetched, `git log -1` on both still reports `fatal: bad object`. They are orphaned, which `scripts/validate_session_json.py:697-703` names squash merge as the most likely cause of. The ADR now says so and draws the consequence Round 1 missed: in the only committed instance of the disagreement, neither field names a commit that exists, so the equality check could not have decided which field was right even in principle. This is a stronger version of the ADR's argument that arrived by accident, through a hook refusing a push.
- **The corpus re-measurement under the implemented behavior confirms the predicted blast radius.** Running `session_qa_binding` over all 1458 committed logs: 366 bind clean, 1 binds with a warning, 1091 still raise. The 1091 are the untouched terminal raise at `:182` (abbreviated `endingCommit` with no resolver supplied by the measurement harness), not the deleted equality raise. Exactly one log changes behavior, which is what the ADR predicted before the code was written.

- **The ADR's own line-number citations go stale on merge.** The implementation adds roughly 28 lines to `.claude/lib/qa_report.py`, so every `qa_report.py:NNN` citation in the ADR, all of which describe the pre-change file, is off by that much in a post-merge tree. Most are in Context and Prior Art, where describing the pre-change state is the point, so they are annotated rather than rewritten: one sentence at the top of Context states the convention. The exception was a forward-looking citation in "The drift can run either way" that pointed a reader at `post_qa_code_changes()`'s `merge-base` call to check current behavior; that one now names the function and the error text, which do not move. Found by re-reading the ADR against the implemented file rather than by any gate.

No design question is reopened. Round 1's decision stands; this entry records evidence that arrived later and the three claims it corrected.

## Round 3 (the genuine six-agent debate, and its conflict resolution)

Round 1 disclosed it was a single-reviewer pass, not six independent agents, and recommended re-running the real debate on a harness with subagent tooling. This round is that re-run: a fresh orchestrating session with the `Agent` tool spawned six independent Phase-1 reviewers (architect, critic, independent-thinker, security, analyst, high-level-advisor), each reading the ADR and the live repository from disk with no visibility into the others' output.

### Phase 1: independent positions

| Agent | Position | Headline finding |
|---|---|---|
| architect | Disagree-and-Commit | Central schema evidence verified real; found "cannot fail open" is false in one sub-case, a missing alternative (a reachability check on `comparison.head` itself), and that `status: accepted` sat alongside the ADR's own text stating the multi-agent bar was not met |
| critic | Accept | Corpus numbers reproduced exactly; found "engages on 35 of 1458" overstates measured production reachability (0 committed logs reach it via `--existing-log`), ~40 stale line citations, stale `implemented: false` |
| independent-thinker | **Block** | Measured 38 of 38 committed `comparison.head` edits also moving `endingCommit` to the same SHA in the same commit, read as contradicting the Context claim that the two fields move independently; also flagged the 23-mention cost figure as misattributed and "cannot fail open" as unpinned by any test |
| security | Accept | Independently reproduced the no-new-capability claim by testing 7 adversarial encodings: 6 of 7 already bypassed the pre-change raise. Found the replacement diagnostic is unreachable from the only automated gate it checked (pre-commit) and that the cited `endingCommit` mitigation fails open on shallow clones |
| analyst | Accept | Verified most citations exactly; found the Round 1 corpus table did not sum (1417+35=1452, not 1458) and confirmed `implemented: false` was stale |
| high-level-advisor | Accept | Verified the schema evidence, the blast-radius re-measurement, and the shipped implementation matching the ADR; raised proportionality (a 10:1 governance-to-code ratio) and one refinement (drop the `validate_session_json.py` `binding.commit` fallback rather than diagnose it) as follow-ups, not blockers |

Five of six returned Accept or Disagree-and-Commit on the Decision. Independent-thinker's Block is the only dissent, and per the debate protocol a Block routes to the high-level-advisor as tie-breaker for Phase 2 conflict resolution.

### Phase 2: conflict resolution (high-level-advisor, tie-breaker, second independent pass)

The orchestrating session named a specific risk before routing the conflict: independent-thinker's 38-of-38 measurement could be a selection-bias artifact of the very check being relaxed (authors manually syncing both fields to satisfy the equality gate, rather than the fields being naturally coupled), and asked the tie-breaker to rule on that explicitly rather than accept the number at face value.

**The selection-bias hypothesis was tested and rejected as unfalsifiable on this data**, not because it is wrong in general but because the control group needed to distinguish it does not exist: every commit that edits `comparison.head` with `endingCommit` present is raise-applicable (the caller supplies `resolve_commit`, so even an abbreviated `endingCommit` resolves), so there is no "raise inert, fields still synced" population to compare against.

**independent-thinker's headline number was itself corrected on re-measurement**: 50 commits edit `comparison.head`, not 38. 38 was the both-full-SHA lockstep subset, reported as the total. Of 44 commits where `endingCommit` is present, 42 move it in lockstep, not 44. The corrected figure is 42 of 44, a strong tendency, not the "38 of 38" invariant the Block leaned on.

**The finding was upheld against the Context, overruled against the Decision.** The tie-breaker confirmed, independently, that the Context's claim ("advanced by two unrelated operations at two different times") does not describe observed practice, and confirmed the `commitHead` schema field documents divergence from the session's own last commit, not from `endingCommit` specifically, per `.agents/sessions/handoffs/2026-08-15-2840-handoff.md:80`. But it also found the lockstep is evidence of the churn the ADR exists to remove, not evidence the raise protects a real invariant: `handoff.md:207` records a PR #4954 reviewer finding that hand-syncing `endingCommit` to a rebind target produces "false historical session provenance" in that field. The Decision was not built on the refuted Context sentence; it rests on `binding.commit` being a rarely-read fallback, the security lens's adversarial-bypass measurement, and the check never reaching a committed log, none of which the 42/44 measurement touches.

**Two of independent-thinker's other findings were separately upheld**: the 23-mention, 15-round cost is misattributed (`handoff.md:227` names `QA_EVIDENCE_PREFIXES` boundary churn, a different mechanism ADR-096 already addressed at its own call site, as the actual driver), and ADR line 98's "the fix that would close that chain" overstated `handoff.md:207`'s actual characterization ("required at minimum") and `handoff.md:219`'s recommended remedy (a new dedicated schema field, not this relaxation).

**Full verdict table** (Issue | Verdict | Priority):

| Issue | Verdict | Priority |
|---|---|---|
| independent-thinker P0: 42/44 lockstep contradicts Context's "unrelated operations" claim | Upheld against Context, overruled against Decision | P1 |
| `commitHead` divergence-target conflation | Upheld | P1 |
| 23-mention/15-round cost misattributed | Upheld | P1 |
| "the fix that would close that chain" overstated | Upheld | P1 |
| critic: "engages on 35 of 1458" should be 0 | Partly upheld (0 via `--existing-log`; a small CI-only residual population does reach it) | P1 |
| analyst: table doesn't sum | Upheld, reproduced with a corrected population of 1459 and an added 6-log third bucket | P1 |
| architect: "cannot fail open" false in a sub-case | Upheld | P1 |
| security: diagnostic unreachable from the only automated gate | Partly upheld (true for pre-commit; the CI residual population does reach it) | P1 |
| security: `endingCommit` check fails open on shallow clones | Upheld | P2 |
| `implemented: false` stale | Upheld | P1 |
| ~40 stale line citations | Partly upheld (disclosure widened to both files) | P2 |
| `_collect_shas` foreign-commit mis-attribution risk | Noted, not caused by this ADR | P2 |
| high-level-advisor's smaller-fix refinement (drop the fallback) | Upheld as a follow-up, not a blocker | P2 |

**Final decision: amend substantially, not accept-as-is and not revert.** The code at `3b05b71d4` is correct and stays; `status: accepted` was already satisfied per `.claude/rules/ci-scripts.md` MUST-NOT-2 before this round began. The Context section, the corpus table, the "cannot fail open" claim, the diagnostic-reachability claim, the misattributed cost figure, and the round-15 characterization are rewritten in this same change per the ruling. A full six-lens re-review was judged disproportionate to a Context rewrite that five of six lenses had already accepted the Decision under; the ruling scoped Phase 4 convergence to independent-thinker and analyst only, the two reviewers whose findings drove the rewrite.

### Phase 4: convergence check (scoped)

independent-thinker and analyst re-reviewed the rewritten Context, corpus table, "laxer direction" section, and diagnostic-reachability section against this same ruling.
