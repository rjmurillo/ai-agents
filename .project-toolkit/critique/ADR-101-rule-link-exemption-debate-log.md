# ADR Debate Log: ADR-101 amendment, generated rule links exempt from the base-ref symlink report

## Summary

- ADR: `.project-toolkit/architecture/ADR-101-enforcement-planes.md`, the "Amended 2026-11-27 (pull request #7730)" text on the Application B dispatcher bullet (line 330).
- Driver: pull request #7730. `Verify dispatch closure against base` failed on the two generated links of the new always-on rule `core`.
- Panel: full six seats (architect, critic, independent-thinker, security, analyst, high-level-advisor), because the change edits executable enforcement (`scripts/ci/_link_exemption.py`).
- Outcome: Consensus after two rounds. Round 1 had three Accept and three Disagree-and-Commit, no Block. Round 2 had six Accept.
- Prior debate log on the same bullet: `.project-toolkit/critique/ADR-101-dispatch-closure-exempt-links-debate-log.md`.
- Claims ledger: `.project-toolkit/critique/ADR-101-rule-link-exemption-claims-ledger.md`. Gate escapes: none in either round.

## How this panel was run, stated plainly

Each seat ran as a separate subagent with a fresh context, in both rounds. All six got the same brief, which held the change, the related work, and the factual-claim verification block. No seat saw another seat's output in Round 1. Round 2 gave every seat one consolidated issue table. One model family ran every seat. The security and analyst seats had read and search tools only, so they marked every claim that needs a command as UNVERIFIED. The author consolidated the findings and made the fixes; the seats did not edit files.

## Writer gates before the panel

| Gate | Result |
|---|---|
| Claims ledger | VERIFIED. One row per factual claim, each with its command and observed result. |
| Documentation accuracy (doc-accuracy Phase 4) | VERIFIED. Eight behavior claims passed against the code. Three low notes: link naming (answered in Round 1 issue 1), two inherited conditions not repeated, and the live test asserting three of four trees (the test now asserts the exact set of four). |
| Self-consistency | VERIFIED. The amendment keeps the invariant and every condition of the 2026-11-16 amendment, and it meets that amendment's rule for a new exempt install tree: a failing pull request and an amendment here. |
| Refuting seat (analyst) | One finding: the cited debate log did not exist. This file closes it. No ledger row was refuted. |

## Related work (Phase 0)

- Issue #7398 and the 2026-11-16 amendment exempted new generated skill links under a fixed condition list. Round 1 of that debate rejected six trees and kept the two skill trees, the only shape a failing pull request had shown.
- Pull request #7523 added a `.claude/lib/memory_enhancement` link. `.claude/lib` is an import root. The owner chose a waiver entry in `.project-toolkit/pr-checks/dispositions.json` over a wider exemption.
- Pull request #7730 adds the rule `core`. The build links it at `.claude/rules/core.md` and `.github/instructions/core.instructions.md`. The base-ref job reported both links at 484e416de4 (2026-11-27).
- A review bot on pull request #7838 raised two points: the code change had no ADR amendment, and no test proved the import-root condition for the new trees.
- The repository owner chose the amendment route on 2026-11-27.

## Change under review

`EXEMPT_ROW_CLASSES` in `scripts/ci/_link_exemption.py` gains the `rules` and `instructions-github` binplace row classes. `is_exempt` does not change. Round 1 reviewed the first amendment text and three new tests. Round 2 reviewed the revised text and a fourth new test.

## Round 1: Phase 1 independent review

Each seat's section is condensed to its vote and its blocking concerns. Issue numbers refer to the consolidation table below.

### Architect review

Vote: Accept. The amendment meets the 2026-11-16 precondition, keeps every condition, and leaves `lib` out.

| Issue | Priority | Description |
|-------|----------|-------------|
| 2 | P1 | The content-loading surface is unnamed. Say which gates still review rule content. |
| 1 | P2 | The Markdown-only premise is not enforced by code. |
| 7 | P2 | Say that the precondition of the earlier debate's narrowing is now met. |

### Critic review

Vote: Disagree-and-Commit. The code change is safe; the text and tests overstate what is enforced.

| Issue | Priority | Description |
|-------|----------|-------------|
| 1 | P1 | The text names `.md` link shapes and `is_exempt` has no suffix check. Add a check with a negative test, or reword. |
| 5 | P1 | The live-closure test reads the environment through `import_roots`. Pin it or state the limit. |
| 2 | P2 | State that rule text steers agents and is outside this check. |

### Independent-thinker review

Vote: Disagree-and-Commit. The invariant holds and the need is shown; one rationale is overstated and a checkpoint is lost without a named replacement.

| Issue | Priority | Description |
|-------|----------|-------------|
| 4 | P1 | "recurs for every new rule" is asserted, not counted. One pull request is the whole evidence base. |
| 2 | P1 | A new always-on rule link no longer forces a human waiver. Name the remaining control. |
| 9 | P2 | The import-root model is Python only. |
| 10 | P2 | #7730 benefits only after this change is on `main`. |

### Security review

Vote: Disagree-and-Commit. The exemption gives a pull request author no capability the author lacks today, because a real file in these trees was never reported. The text omits the content-review gap.

| Issue | Priority | Description |
|-------|----------|-------------|
| 1 | P1 | No suffix condition. Add one, or state that any file type may link. |
| 3 | P1 | `.github/CODEOWNERS` has no entry for the plugin or install rule trees. State it or flag it. |
| 8 | P2 | `exists()` accepts a directory target. |

Checked and closed by this seat: traversal (the link text must equal the binplace text and the name holds no slash), a symlinked target component (rejected), and time-of-check races (the job reads the head from the object store as data, with read-only permission and no secret).

### Analyst review

Vote: Accept. No condition is relaxed and every claim the seat could read holds.

| Issue | Priority | Description |
|-------|----------|-------------|
| 2 | P1 | State the content-risk consequence. |
| 6 | P1 | No test puts a real file in an exempt tree. |
| 1 | P2 | The Markdown-only fact is not an enforced condition. |

### High-level-advisor review

Vote: Accept. Amending is the right call over a second waiver; the change is one frozenset literal.

| Issue | Priority | Description |
|-------|----------|-------------|
| 2 | P2 | State that exemption does not review content. |
| 7 | P2 | Say why the other `link: true` rows stay out. |
| 4 | P2 | The recurrence claim has no count. |

## Consolidation and resolution

| # | Issue | Priority | Resolution |
|---|---|---|---|
| 1 | Link shapes and "Markdown only" read as conditions; no suffix check exists | P1 | Reworded, no code change. The text says the conditions do not test the file type, and marks the Markdown fact as context. The invariant rests on the closure-path and import-root conditions, which do not depend on file type. A per-class suffix map would add a second condition list with no failing case behind it. |
| 2 | Content-loading consequence and the lost report cue not stated | P1 | Added a consequence sentence and the three content controls: pull request review, the `/templates/rules/` CODEOWNERS entry, and `build_all.py --check`. A control run confirmed the drift gate fails on a hand-edited generated rule. |
| 3 | No CODEOWNERS entry for the plugin or install rule trees | P1 | Deferred with reason. True and outside this change. The drift gate ties the generated copies to the owned template. Flagged to the owner in the pull request body. |
| 4 | Recurrence asserted, not counted | P1 | Reworded to "One pull request has shown the need; each later pull request that adds a shipped rule adds its generated links." |
| 5 | Live-closure test reads the environment | P1 | Kept ambient on purpose and said so in the test docstring. The environment adds only `lib` directories inside the work tree. A root that puts one in an exempt tree is a case the test must report. |
| 6 | No real-file test | P1 | Added `test_a_real_file_in_an_exempt_tree_is_never_exempt`. |
| 7 | Other `link: true` rows; earlier narrowing | P2 | Added one sentence: the other rows stay reported; the amendment admits only the two trees demonstrated by #7730. |
| 8 | Directory target | P2 | Recorded. Skill links target directories by design under the same check. |
| 9 | Python-only import-root model | P2 | Recorded. The 2026-11-16 residual risk covers run-time paths the gate does not model, now for four trees. |
| 10 | #7730 benefits only after merge | P2 | Recorded. By design, the base copy decides. |

## Round 2: Phase 4 convergence check

| Seat | Vote | Note |
|---|---|---|
| architect | Accept | Issues 1, 2, and 7 resolved. No refuted claim in the changed text. |
| critic | Accept | Issue 1 resolved by rewording. Issue 5 accepted as a note: a developer with a plugin root inside an exempt tree gets a local failure, which is the intended report. |
| independent-thinker | Accept | Issues 4 and 2 resolved. Issues 9 and 10 acceptable as recorded. |
| security | Accept | Issues 1, 2, and 8 resolved. Issue 3 deferred with a sound reason; keep it on the owner's list. |
| analyst | Accept | Issues 1, 2, and 6 resolved. The seat could not rerun the command-based controls. |
| high-level-advisor | Accept | Issues 2, 4, and 7 resolved. One new P2: "names or imports" could be read to include comment mentions. |

The critic marked the implied suffix condition REFUTED in Round 1; issue 1 removed that implication. No seat recorded a REFUTED claim in Round 2. Claims a seat marked UNVERIFIED were command results the seat could not rerun (the CI log, the negative controls, the drift control); each has a VERIFIED ledger row with its command.

## Strategic review

| Lens | Assessment |
|---|---|
| Chesterton's fence | PASS. The report exists because the gate refuses an unpinned link while it builds the closure. The amendment keeps the report and every condition, and adds two trees the closure does not reach. |
| Path dependence | PASS. Rollback is one frozenset edit, proven by a negative control. |
| Core versus context | Not applicable. |
| Second-system effect | PASS. Two classes, no new condition, no new mechanism. |

## Outcome

Consensus: six Accept in Round 2. The decision is accepted as amended. ADR-101 keeps `status: accepted`; the frontmatter does not change.

Flagged for the owner, not fixed here: `.github/CODEOWNERS` has no entry for `src/claude/rules`, `src/copilot-cli/instructions`, `.claude/rules`, or `.github/instructions`.

## Post-consensus note

After Round 2 the author applied the one new P2 from the high-level-advisor seat. "no closure script names or imports a path in either" became "no root, closure path, or import root of the gate lies in either", which is what `test_the_live_closure_stays_clear_of_every_exempt_install_tree` checks. The ledger row changed with it. The reason for retaining other rows was also narrowed to the two trees demonstrated by #7730, since #7523 had shown a different tree.
