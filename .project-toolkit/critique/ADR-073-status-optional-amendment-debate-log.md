# ADR Debate Log: ADR-073 Amendment 2026-09-29, Prose Status Is Optional

## Summary

- **Rounds**: 1 of 10 (Phase 1 independent review plus one convergence vote)
- **Outcome**: Concluded Without Consensus. Three roles Block on one P1 text finding.
- **Final Status**: needs-revision. Frontmatter stays `status: accepted`; one line of the amendment needs correcting before merge.
- **Review independence**: one model played all six roles in separate passes. This is not six independent reviews. Treat the votes as one reviewer's six lenses.
- **Artifact reviewed**: `.project-toolkit/architecture/ADR-073-adr-lifecycle-frontmatter.md`, the six amended places (lines 42, 57, 101, 105, 129, 137) and the new section "Amendment 2026-09-29: prose Status is optional" (lines 163 to 173).
- **Ground truth**: working tree of branch `fix/5242-adr073-status-optional` against `origin/main` at `4f43bb189` (47 files, 215 insertions, 211 deletions).
- **Owner decision under review**: option A from issue #5242. Prose `## Status` is optional, and forbidden only when it merely restates the frontmatter status enum.

## Phase 0: Related Work

| Item | State | Relevance |
|---|---|---|
| #5242 | open, 0 comments | The work item. Warns that two earlier implementations turned line 57's "may" into a rule the ADR did not state, in opposite directions. Asks to change the decision, not route around it in a validator. Its definition of done requires correcting `ADR-005-status-duplication-debate-log.md:65` in the same change. |
| #5273 | open | Per-check ratchet compares totals, so fixing one violation and adding another under the same key nets to zero. Folding a second defect into `prose-frontmatter-agree` widens what one key hides. |
| #5196 | referenced | Template-required sections across the corpus. |

## Evidence Gathered

- ADR diff has exactly six hunks at lines 42, 57, 101, 105, 129, 137, plus the new section. Each matches the six places the issue lists verbatim.
- `scripts/validation/check_adr_lifecycle.py`: `_RESTATEMENT_RE` (line 626), `_status_section_lines` (line 634), `_restates_status` (line 654), and the new branch in `_check_prose` at line 709 to 716 emitting `Violation("prose-frontmatter-agree", ...)`. `CHECKS` (lines 148 to 157) is unchanged at eight names. `grep status-section-redundant` over the validator returns no match.
- `_parse_baseline_payload` (line 948) rejects a payload whose keys differ from `CHECKS` in either direction. `_counts_at_ref` (line 1063) returns None on that rejection. Its caller (lines 1022 to 1028) turns None into `EXIT_CONFIG`. So a PR that adds a check name fails its own base-ref comparison, because the fork-point baseline lacks the new key. The folding claim holds.
- Validator run: `uv run --frozen python scripts/validation/check_adr_lifecycle.py` returned `[PASS] 0 violation(s) across 112 ADR record(s)`, exit 0. `adr_lifecycle_baseline.json` is unchanged; `prose-frontmatter-agree` baseline is 0.
- Tests: `tests/validation/test_check_adr_lifecycle.py` and `test_check_adr_lifecycle_base_ref.py` returned 151 passed.
- Corpus replay: applying `_restates_status(_status_section_lines(body))` to every `ADR-*.md` on `origin/main` flags exactly 33 files. The set of changed ADR files minus ADR-073, README and ADR-TEMPLATE equals that set, with no extra and none missing. Every flagged line is either `Accepted` or `Proposed`.
- Spot checks of three deletions (ADR-001, ADR-032, ADR-070): each hunk removes only `## Status`, one blank line, the single enum word, and one blank line.
- ADR-022's fenced sample `## Status` at line 528 sits inside the fence opened at line 525; with its real section deleted the validator still passes, so the trap #5242 names did not fire.
- Regex probe on `_restates_status` with single lines: flagged `Superseded 2026-01-01 by ADR-042`, `Accepted by ADR-005`, `Deprecated by ADR-09.`, `Accepted (2026-06-19).`; not flagged `Superseded by [ADR-042](ADR-042-x.md)`, `Superseded by ADR-042 on 2026-01-01`, `Accepted, 2026-06-19`, `Accepted on 2026-06-19`, `Superseded by: ADR-042`, `Accepted 19 June 2026`.
- Regex timing: `"Accepted" + " " * n + "x"` took 0.023s at n=2000, 0.31s at n=8000, 4.3s at n=32000. Quadratic backtracking.

## Phase 1: Independent Reviews

### architect

Strengths: line 57 now states one rule: optional; permitted for nuance; forbidden when it only restates (enum word alone, or with a date or the `superseded-by` target); frontmatter wins on disagreement. Lines 42, 101, 105, 129 and 137 agree with it. Line 137 is rewritten rather than qualified, as #5242 asked. The decision was changed in the ADR first, which is the governance path the issue demanded.

Weakness: amendment line 170 says a restating section is a `status-section-redundant` violation. No such check exists. The validator reports it under `prose-frontmatter-agree`, and `ADR-TEMPLATE.md:34` already says so. The ADR and the template now name different checks for the same rule. That is the exact drift class this ADR exists to prevent.

| Issue | Priority | Description |
|---|---|---|
| A1 | P1 | ADR line 170 names a nonexistent check; code and template use `prose-frontmatter-agree`. |

### critic

Is the rule implemented exactly, no stronger? Mostly. The validator never requires presence (no-section returns empty, test coverage exists). It flags only a one-line section whose lead word already equals the frontmatter status. Measured deviations, none present in the corpus:

- Weaker than line 57: a linked successor (`Superseded by [ADR-042](...)`), a date after the successor, `on <date>`, comma or colon separators, non-ISO dates, and a restatement split over two lines all pass.
- Stronger than line 57: `<enum> by ADR-N` is flagged for any status, and the successor id is not compared with the frontmatter `superseded-by`, so a prose line naming a different successor is reported as a restatement to delete rather than as drift.

| Issue | Priority | Description |
|---|---|---|
| C1 | P1 | Same as A1. |
| C2 | P2 | Regex narrower than the rule for link, `on <date>` and punctuation variants. |
| C3 | P2 | Regex broader than the rule for `by ADR-N` on non-superseded statuses and an unmatched successor id. |

### independent-thinker

Is deleting 33 sections scope creep? No. With the `prose-frontmatter-agree` baseline at 0, leaving them would put 33 violations above baseline and fail the corpus gate the issue's definition of done requires. The replay proves the deleted set is exactly the set the rule forbids, and every line deleted was a lone enum word. The deletion is the rule's direct consequence, not an adjacent cleanup.

Challenge on the fold: the claim that a new check name would be refused holds, but it describes a limitation in the baseline reader, not a reason the two defects belong to one name. One key now counts two different author mistakes (disagreement and redundancy). With the baseline at 0 the masking #5273 describes cannot bite today; it would once a nonzero count is recorded. The ADR should say the rule reports under `prose-frontmatter-agree` and why, not invent a name.

| Issue | Priority | Description |
|---|---|---|
| I1 | P2 | Folding couples two defects under one ratchet key; tie to #5273. |

### security

`_RESTATEMENT_RE` has adjacent quantified classes that both match whitespace (`[*_\`~\]\s]*` then `[.\s]*`). Measured quadratic time: 4.3s for a 32000-space line. Input is repository text, so the only party who can trigger it is a PR author slowing their own gate run. Low severity. A possessive quantifier or non-overlapping classes removes it. No new file, network or secret surface. The deletion of 33 sections does not touch frontmatter, so no `status` value changed and no acceptance signal was forged.

| Issue | Priority | Description |
|---|---|---|
| S1 | P2 | Quadratic regex backtracking on long whitespace runs. |

### analyst

Verified every claim in the caller's brief against code: `_restates_status`, `_status_section_lines` and `_check_prose` implement option A with the deviations C2 and C3; the folding claim holds for the reason given; 33 deletions equal the forbidden set. The ADR-005 debate log edit corrects a sentence #5242 flagged as false; verified on `origin/main` that ADR-024, ADR-025, ADR-042 and ADR-055 have zero `## Status` headings. That edit is in scope by the issue's definition of done.

| Issue | Priority | Description |
|---|---|---|
| N1 | P1 | Same as A1, confirmed by grep. |

### high-level-advisor

The decision is coherent and matches the owner's direction without the two earlier failure modes: presence is not required, and the section is not banned outright. One wrong check name in the amendment is the only thing standing between this and Accept. Fix line 170 to say the gate reports it as `prose-frontmatter-agree`, and optionally one sentence on why no new check name was added. The regex deviations are P2 and belong in the PR body, not the ADR.

## Phase 2: Consolidation

Consensus points: one coherent rule; the validator never demands presence; deleting 33 bare sections is required by the gate and exactly bounded; the folding claim holds.

Conflicts: whether the regex deviations (C2, C3) are P1 because the caller asked for "no stronger rule". Ruling by high-level-advisor: P2. No corpus record triggers either direction, tests pin the shapes the owner named, and the stronger shapes are edge forms nobody has written.

Anti-pattern check: no Pass Through or Copy Edit. A1 looks editorial but names a check that tooling and readers would search for and not find.

## Phase 3: Proposed Resolutions

| Finding | Resolution proposed to the ADR author |
|---|---|
| A1, C1, N1 (P1) | Line 170: replace `` `status-section-redundant` `` with `` `prose-frontmatter-agree` ``, and add that no new check name was introduced because `_parse_baseline_payload` refuses a baseline whose keys differ from `CHECKS`. |
| C2, C3 (P2) | Record in the PR body; widen or tighten `_RESTATEMENT_RE` in a later change if a real record hits it. |
| I1 (P2) | Note the coupling on #5273. |
| S1 (P2) | Record in the PR body. |

The reviewer did not edit the ADR. No resolution is applied yet.

## Phase 4: Convergence Vote (Round 1)

| Agent | Position | Notes |
|---|---|---|
| architect | Block | A1 open: ADR and template name different checks. |
| critic | Block | A1 open; C2 and C3 recorded as P2. |
| independent-thinker | Disagree-and-Commit | Deletion justified; wants the fold explained (I1). |
| security | Disagree-and-Commit | S1 is low severity, record it. |
| analyst | Block | N1 open, confirmed by grep. |
| high-level-advisor | Disagree-and-Commit | Decision sound; one-line text fix required before merge. |

Result: 0 Accept, 3 Disagree-and-Commit, 3 Block. Consensus NOT reached. This is not agreement.

## Next Steps

The ADR author corrects line 170, then a second round re-votes. No issue was filed by this review.

## Round 2: Re-verification of P1 Findings

Same reviewer, same single-model caveat: one model played all six roles. Each claim below was checked against the working tree, not taken from the author's summary.

| Finding | Evidence in the file | State |
|---|---|---|
| A1, C1, N1 | ADR line 170 now reads "A section that only restates the enum is a `prose-frontmatter-agree` violation, reported for deletion." A grep for `status-section-redundant` over `.project-toolkit/architecture`, `scripts/validation`, `templates` and `.claude/skills/adr-generator` returns no match. The ADR, the template and the validator now name the same check. | Closed |

Gates rerun at the round 2 tree: `check_adr_lifecycle.py` returns `[PASS] 0 violation(s) across 112 ADR record(s)`, and the two lifecycle test files return 152 passed (151 in round 1, plus the new long-line test). The ADR still contains 0 em or en dashes.

P2 status after round 2:

- S1 closed: `_MAX_RESTATEMENT_LINE = 200` (validator line 637) is checked at line 668 before the regex runs, and `tests/validation/test_check_adr_lifecycle.py:620-622` drives a 32000-space line. A single line longer than 200 characters is now never treated as a restatement, which makes the regex slightly narrower than line 57's rule. No corpus record is affected.
- C2 open: the regex misses linked successors, "on <date>", commas and colons. Non-blocking.
- C3 open: `<enum> by ADR-N` is flagged for any status, and the successor id is not compared with `superseded-by`. Non-blocking.
- I1 open: two defects still share the `prose-frontmatter-agree` count, and the ADR does not say why no new check name was added. Tie to #5273. Non-blocking.

### Agent Positions (Round 2)

| Agent | Position | Notes |
|---|---|---|
| architect | Accept | A1 closed; the ADR, template and code agree. |
| critic | Accept | C1 closed; C2 and C3 recorded as P2. |
| independent-thinker | Disagree-and-Commit | I1 remains: the fold is undocumented in the ADR. Not blocking. |
| security | Accept | S1 closed, and it has a test. |
| analyst | Accept | N1 verified by grep, and both gates rerun green. |
| high-level-advisor | Accept | No blocking text remains. |

Result: 5 Accept, 1 Disagree-and-Commit, 0 Block. Consensus reached in round 2 of 10. The single-model caveat above still applies: this is one reviewer's six lenses, not six independent reviews.

## Author note: records touched by the corpus sweep

This section is added by the change author, not by a review role, and carries no vote. The panel reviewed the sweep as part of the amendment, and the reviewer spot-checked three hunks. Each record below lost a `## Status` section that held one word only ("Accepted" or "Proposed") matching its frontmatter `status`. The lifecycle gate flagged exactly these 33 records after the rule change, so leaving them would have raised `prose-frontmatter-agree` above its baseline of 0.

Records: ADR-001, ADR-008, ADR-009, ADR-010, ADR-011, ADR-012, ADR-013, ADR-015, ADR-016, ADR-019, ADR-021, ADR-022, ADR-026, ADR-029, ADR-032, ADR-034, ADR-038, ADR-043, ADR-045, ADR-046, ADR-048, ADR-049, ADR-050, ADR-051, ADR-053, ADR-059, ADR-060, ADR-065, ADR-067, ADR-070, ADR-088, ADR-093, ADR-099.

Verification: `uv run python scripts/validation/check_adr_lifecycle.py` reports 0 violations across 112 records after the sweep. No record changed anything except that one section.

