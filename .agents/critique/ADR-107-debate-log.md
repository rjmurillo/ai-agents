# ADR Debate Log: Canonical Skill Contracts and Generated Harness Projections

Record under review: `.agents/architecture/ADR-107-canonical-skill-contracts-and-harness-projections.md`
Tracker: issue #5603. Branch: `feat/adr-canonical-skill-contracts-5603`.

## Summary

- Rounds: 1
- Seats: 6 (architect, critic, independent-thinker, security, analyst, high-level-advisor)
- Round 1 outcome: **3 Block, 3 Disagree-and-Commit.** No consensus on revision 1.
- Disposition: revision 2 written against every P0 and every P1. Consensus not re-polled;
  the record ships as `proposed` with the dissent recorded below.
- Final status: proposed, `implemented: false`, `review-by: 2027-03-09`.

Each seat received the artifact and nothing else. None saw the reasoning that produced it, and
none saw another seat's findings. Every finding below was re-verified against the tree by the
author before it was accepted or rejected; three agent claims were checked and one was found
wrong (see "Findings rejected").

## Agent positions

| Agent | Round 1 vote | Load-bearing objection |
|-------|--------------|------------------------|
| architect | Block | Two `repo-observed` citations were false: a stale line number sourced from a pytest fixture copy, and issue #3465 treated as an open gap tracker when it is closed as completed |
| critic | Block | `build_all.py --check` exited 2 on the branch: the generated ADR index was not regenerated. The record's own C1 class, red on the record shipping it |
| security | Block | Invariant 6 is already unverified on the trunk (`push-pr` argument-scoped `allowed-tools` copied verbatim to a harness with no committed permission surface); provenance class was assigned by file path, which any pull request can choose; the fail-closed branch named no branch |
| independent-thinker | Disagree and commit | The predicate could not be declared where the record said: only one of three platform configs has an `artifacts` stanza, and every class needing a `none` baseline sits outside it, making the stated rejection criterion unfalsifiable |
| analyst | Disagree and commit | Citation audit: one fabricated claim, one truncated enum range, three mis-anchored line numbers, and label discipline violated by the record's own table |
| high-level-advisor | Disagree and commit | Evidence and decision were mismatched: the flagship incident (PR #5059) was caught by CI, so it motivates C1 and not C3, and the eight invariants carry no measured instance at all |

## Key issues addressed in revision 2

**Two false `repo-observed` citations, both removed.** The "line 435" claim about
`ai-agents-architecture-contract/SKILL.md` was read from `build/audit/pytest-4870/`, a pytest
fixture capture, not the source tree. Commit `72f0e6309` (PR #5640, merged 2026-09-08) had
removed the string one day earlier. The correction now sits inside the record, with the
generalizable lesson: a path under `build/audit/` is a captured artifact, and reading one produces
a citation that is checkable, wrong, and confidently labeled. In a record that defines evidence
labels, that was the disqualifying defect.

**Issue #3465 verified closed as completed; M4 rescoped.** `check_skill_md_portability.py:315-318`
puts `templates/agents` in `EXTRA_SCAN_ROOTS`, so canonical agent prose is scanned. What is
uncovered is agent **outputs**, stated verbatim at `:52`. M4 and issue #5689 were both corrected.
The same stale #3465 reference in `.claude/rules/plugin-self-containment.md` is flagged, not
fixed; it is a rule file with its own review requirements.

**The generated ADR index was stale.** `build/scripts/build_all.py --check` exited 2 on the branch
because `.agents/architecture/README.md` had not been regenerated after adding ADR-107. Fixed by
running the generators in the documented order (`sync_plugin_lib.py`, then `build_all.py`) and
committing the result. The finding is the strongest evidence in the round that C1 is real: the
record's own conformance class was red on the branch shipping the record.

**The predicate moved from `templates/platforms/*.yaml` to
`.agents/governance/GENERATOR-FILES.md`.** Verified: `vscode.yaml` and `visual-studio.yaml` carry
no `artifacts` stanza, and `copilot-cli.yaml`'s covers five generator-owned classes. Every class
needing a `none` baseline (the three hand-maintained agent trees) is outside that file, so the
original scoping would have declared a predicate only for classes that already have a working
gate and emitted zero `none` rows. The governance register is the only surface reaching both
kinds of tree.

**The rejection criterion was unfalsifiable and was rewritten.** It measured a majority of YAML
stanzas; it now measures the classes in "Dependent artifact classes", and a second criterion was
added covering the case where invariants 6 and 8 turn out to hold trivially everywhere.

**Section 5 relabeled `hypothesis`, with an enforceability table.** No measured case exists of a
projection silently dropping an invariant. Six of the eight have no extractor and are now marked
advisory; only invariant 6 (`allowed-tools`) and invariant 8 (documented exit codes) are
machine-checkable today, and the pilot asserts those two only. The record now states outright
that a pilot reporting the other six green would be measuring nothing.

**Invariant 6 is recorded as unverified on the trunk, with an owner.**
`.claude/skills/push-pr/SKILL.md:6` and `src/copilot-cli/skills/push-pr/SKILL.md:6` carry an
identical argument-scoped `allowed-tools` line; `translate_allowed_tools` respells `mcp__*`
identifiers only. Whether Copilot honors, ignores, or widens argument scoping is unprobed and is
labeled `hypothesis`. Issue #5691 owns settling it. The pilot was re-pointed to `push-pr`
alongside `security-scan`, because `push-pr` is the only pilot input that can fail.

**Provenance is assigned by plane, not by path.** A directory name cannot separate mandatory
policy from attacker-supplied text when any pull request can add a file to either directory. The
record now states that repository policy authored inside the change under review is external
content for that change, closing the shape ADR-101 exhibits at issue #4402.

**The fail-closed branch is named concretely**: the class carries `none`, the projection for that
harness is refused via `excludeFilenames`, and M2 ships a negative control that fails if the
artifact ships anyway. "Byte-identical text, therefore the invariant is preserved" is called out
as the permissive branch wearing a compliant label.

**The adapter exception grew an eighth condition and a floor.** No count of satisfied process
conditions buys a change to invariant 5 or 6, and a capability cell authored in the same change
no longer satisfies condition 2.

**Smaller corrections.** `CONFIG` added to the evidence-kind enumeration and the range fixed to
`_harness_capability.py:52-73`; issue #5423 restated as open rather than shipped; REQ-003-010
re-cited to `build_all.py:788`, `:2221`, `:2227`; the filenames-only claim re-anchored to
`claude-agents.md:52`; rule-file assertions relabeled `docs-say`; a `Decision Drivers` section
added with five drivers, and the alternatives table rescored against them; the predicate
vocabulary collapsed from four values to three (`byte` is `derived` with an identity transform);
the `GENERATOR-FILES.md` six-row versus `GENERATORS` seven-entry delta stated rather than papered
over; Prior Art given an author.

**The shipped test was rewritten and probed.** The first version asserted that at least five
backticked paths in the section resolved. The critic seat constructed four passing mutations
against it, including deleting the two rows covering the record's motivating incident, and the
advisor seat found that its path regex dropped both gates C1 actually invokes because their
backtick spans carried a trailing flag. The rewrite asserts the class-id set is exactly C1 to C6
and that every row either names an existing gate or carries an explicit missing marker.
Discrimination probes run before commit: deleting the C2 row fails
`test_every_conformance_class_has_a_row`; renaming C1's gate fails
`test_every_cited_path_resolves[C1]`; the restored file is byte-identical and all 20 tests pass.

## Findings rejected, with reasons

- **Fold M1 into this pull request (advisor F3, echoed by two seats as "M0 alone enforces
  nothing").** Issue #5603's implementation boundary scopes this change to the ADR plus small
  scaffolding and directs implementation slices to follow-up issues. The owner set that boundary;
  the seats' preference does not override it. The objection is answered partially instead: the
  Status section now states plainly that the record enforces nothing until M1, and the shipped
  test was strengthened so it fails for a real reason rather than only for a renamed file.
- **Collapse the six layers to three (independent-thinker F8).** Issue #5603's acceptance criteria
  require the record to distinguish all six by name. The seat's underlying point is correct and
  was incorporated instead of the change: the layers table now marks host authorization as a
  boundary and generated output as the projection layer's product, rather than presenting six
  peers.
- **The analyst seat could not verify any GitHub issue state** (no `gh` in its tool set) and
  flagged every issue claim as unverified. The author cleared all of them with `gh issue view` on
  2026-09-09, and the References section now records that.

## Not resolved, carried forward

- **The record enforces nothing until M1 (#5686).** Three seats named this. It is a deliberate
  consequence of the tracker's implementation boundary, not an oversight.
- **A `none` count ratchet and per-row expiry do not exist yet.** They are M1 acceptance criteria.
  Without them, `none` legalizes the status quo under a new name, which is the six-month regret
  the advisor seat named and the record's Negative section repeats.
- **"A skill cannot grant itself access" has no enforcing mechanism on either harness.** The
  record states the gap rather than claiming enforcement it lacks.
- **Six of the eight invariants have no extractor** and stay advisory until one is named. Naming
  one is out of scope here and is not smuggled into a follow-up as though it were scoped.
- **Consensus was not re-polled after revision 2.** Three seats voted Block on revision 1, and
  each named its unblock conditions; those conditions are addressed above. A second round would
  strengthen the record and is the obvious next step if the owner wants the vote on file.

## Post-review gate findings

Two repository gates found defects after the seats reported. Both are recorded here because they
are the same class of failure the round was hunting: a claim that reads correctly and does not
hold.

**`scripts/validation/check_citation_freshness.py` rejected eight of the record's citations.**
The gate reads the anchors a citing line names and checks they appear at the cited lines. Eight
citations named only the evidence label (`repo-observed`, `docs-say`) and no text from the source,
so nothing tied the line number to the content. Fixed by quoting real text from each cited
location, which is what `.claude/rules/canonical-source-mirror.md` asks for anyway. No
`citation-freshness: ignore` marker was used; suppressing the gate on a record about evidence
quality would have been the wrong trade.

**The taste count ratchet went to 567 against a baseline of 566.** The record is 671 lines, over
the 500-line file-size rule. It takes the documented escape, a `# taste-lint: ignore file-size`
comment with a reason, following the ADR-085 precedent for an accepted record whose value is its
audit continuity. The baseline was not raised.

## Verdict

Revision 2 ships as `proposed`. Every P0 from every seat is addressed in the record or in a linked
issue, the two false citations are removed and their root cause is documented inside the record,
and the branch's own C1 gate is green. The dissent above is part of the record rather than a
footnote to it: the strongest objection, that M0 governs without enforcing, is true, and the
tracker scoped it that way on purpose.

## Round 3: evidence-only correction (self-review, issue #5456)

**Trigger**: the R3 section cites `src/copilot-target-emitter.ts`, `src/types.ts`,
`src/agent-registry-schema.ts`, `src/transforms/command-syntax-translator.ts`, and their tests at
`tests/copilot-target-emitter.test.ts` and `tests/command-syntax-translator.test.ts` as orphaned
evidence for the cost of a second registry system. The 2026-09-04 ponytail audit (finding 9)
confirmed those six files still have zero readers and no root `package.json`/`tsconfig.json`
wiring them to any runner, and issue #5456 deleted them in this same cohort (commits
`0312411`, `b4875a7`).

**Scope**: this round is a self-review of a single evidentiary sentence, not a re-litigation of
R3. The decision (reject a second registry/routing/generation system; extend
`GENERATOR-FILES.md` and `templates/platforms/copilot-cli.yaml` instead) is unaffected by whether
the orphaned files it cites still exist on disk. Re-running the full six-seat debate over a tense
change would be Copy Edit (Zimmermann): the content under review has not changed.

**Verification performed**: read the R3 paragraph in full; confirmed via `git log` and `git
status` in this session that the six named files were removed by the two commits above; confirmed
no other paragraph in this ADR depends on the files existing (grepped the whole document for each
basename before editing).

**Position**: self-review. Accept the edit: it changes verb tense and adds the deletion citation,
and changes no other word in the R3 paragraph or the decision it supports.

### Outcome

Accepted. The evidence sentence now reads in the past tense and names the deleting commits; the
R3 decision, its rationale, and every other section of the record are unchanged.
