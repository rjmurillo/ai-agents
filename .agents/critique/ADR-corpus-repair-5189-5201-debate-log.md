# Debate Log: ADR Corpus Repair Batch (issues #5189 to #5201)

## Subject

Ten modified records: ADR-005, ADR-023, ADR-024, ADR-025, ADR-032, ADR-033, ADR-042, ADR-055, ADR-079, ADR-092.

Grouped as three change-sets:

- **CS-1 runner selection.** ADR-024 and ADR-025 to `status: superseded`, `superseded-by: ADR-055`. ADR-055 gains the reciprocal `supersedes: [ADR-024, ADR-025]`, a real `## Status` section replacing an inline bold-label line, and a corrected exception marker.
- **CS-2 version bump chain.** ADR-079 `superseded-by` moved from ADR-092 to ADR-091. ADR-092 `supersedes` narrowed from `[ADR-079, ADR-091]` to `[ADR-091]`.
- **CS-3 scripting language and links.** ADR-005 to `superseded` by ADR-042. ADR-042 to `accepted`, `supersedes: [ADR-005]`. ADR-023, ADR-032, ADR-033 receive link repairs only.

The batch's own claim is that these are transcription of decisions the repository already made, not new decisions. The debate was convened to test that claim, because ADR-073 states that "a hand-edit of frontmatter to `accepted` MUST NOT be treated as governance approval."

## Roster and verdicts

| Role | Verdict | Core position |
|---|---|---|
| architect | ACCEPT | Corpus measurably more coherent: `frontmatter-parses` 59 to 54, `supersession-reciprocal` 1 to 0. Resolve the ADR-042 evidence citation in this change. |
| critic | BLOCK, resolved | Three P0s in CS-1: a false claim that a live accepted ADR was retired, a self-falsifying citation, and `implemented: true` closing an open compliance gap. All three fixed; see Resolutions. |
| independent-thinker | DISAGREE-AND-COMMIT | The transcription frame is real for most hunks but does not cover three: a coined exception marker, an unevidenced enum, and unverifiable archaeology. Label them. |
| security | DISAGREE-AND-COMMIT | The ten records are correct. Dissent recorded against the gate that authorized them, which is forgeable (see Gate findings). |
| analyst | DISAGREE-AND-COMMIT | One P0: the batch's own new prose fabricated ADR-055's provenance. Refuted against primary sources and corrected. |
| high-level-advisor | ACCEPT | Land it. Four of six deferrals were decidable by evidence and should not have been deferred. |

**Consensus: reached.** Two Accept, three Disagree-and-Commit, one Block whose blocking findings were resolved before merge. No unresolved P0.

## The central question: is ADR-042 to `accepted` a forgeable approval?

**No.** Three independent confirmations.

1. `.agents/critique/ADR-042-debate-log.md` records a real six-role debate dated 2026-01-17, `**Final Verdict**: ACCEPT`, 5 Concerns plus 1 Accept resolved Disagree-and-Commit, all P0 findings marked RESOLVED. Four supporting artifacts sit beside it: `ADR-042-independent-review.md`, `ADR-042-security-review.md`, `ADR-042-strategic-advisory.md`, `ADR-042-python-migration-critique.md`.
2. The diff adds a frontmatter block and changes not one character of the `## Status` body, which already read `Accepted` at HEAD.
3. `AGENTS.md` ("Always: Python (ADR-042)") and `.claude/rules/universal.md` SHOULD-3 have bound on ADR-042 as accepted for seven months.

The deciding principle, from the tie-breaker: **frontmatter is a machine-readable index of the record's own prose, not a decision surface. Adding it is legitimate when the value is copied from a statement already standing in the tree under the owner's merge, and the prose is left unedited.** The forgery concern applies to a different edit shape, writing `accepted` into a record whose prose says Proposed or says nothing. That shape does not appear here.

**This log is not the authorizing evidence for ADR-042 and must not be cited as such.** The authorizing evidence predates it by seven months and is a separate artifact with its own verdict. Were this log the only evidence, the review would be circular.

**The precedent does not extend.** Six records carry `implemented: true` against `status: proposed`: ADR-075, ADR-077, ADR-078, ADR-089, ADR-093, ADR-098. Each has a debate log that explicitly withholds acceptance, and ADR-098 states the pair is deliberate. They were left untouched. Do not read ADR-042 as license to flip them.

ADR-024 and ADR-025 do **not** clear on transcription: their own prose said `Accepted` and this batch rewrites it to `Superseded`. They clear on a narrower principle: **a supersession asserted in the successor's accepted prose is binding on the predecessor, because supersession is a relation and recording only one end of it is the defect.** ADR-055 has asserted it since 2025-12-29.

## Resolutions applied before merge

| Finding | Raised by | Resolution |
|---|---|---|
| P0. ADR-055 claimed `# ADR-014 Exception:` was "retired along with their records". ADR-014 is `Distributed Handoff Architecture`, accepted and live, bound by `universal.md` MUST-3. | critic | Rewritten. The prose now states that ADR-014 today is the handoff decision and that a reader following the marker to its number lands there. |
| P0. ADR-055 cited "the Phase 3 checklist and the Windows exception example below, both of which still carried the ADR-007 number" while the same diff corrected one of them. | critic | Claim removed. It was also unverifiable; see the analyst P0 below. |
| P0. `implemented: true` on ADR-055 while 21 of 132 `runs-on` declarations are non-ARM and **zero** carry an exception marker in any spelling. | critic, security | Set to `implemented: false`. The Metrics table's stale `0 (0%)` figure now carries the 2026-08-21 measurement and states plainly that the ARM-first preference is in force while the exception-documentation requirement is not. |
| P0. ADR-055's provenance prose was fabricated: it claimed PR #476 on 2025-12-29 renumbered this file. | analyst | Refuted against primary sources and corrected. `mcp__github__list_commits` on the path returns a single commit, `3e24d2c0`, from PR #1604 on 2026-04-10, "renumber duplicate ADR-032 and ADR-051 to ADR-055 and ADR-056". This record **was ADR-032**. |
| P1. ADR-042 carried the enum without citing its evidence, while ADR-073 cites its own log path inline. | architect, security, independent-thinker | `## Status` now names the debate log and its four supporting artifacts, with the reason. |
| P1. ADR-025 stated "111 of 127 `runs-on` declarations" with no matcher. Measured total is 132. | critic, architect, independent-thinker, analyst | Corrected to 111 of 132, with the command and a note that 5 are `${{ matrix.os }}` expressions expanding to further non-ARM jobs. |
| P1. The `# ADR-055 Exception:` spelling is coined here, not restored. | independent-thinker | Stated in the record as new, with the note that no validator reads the pattern. |
| P1. ADR-024 cited bare SHAs unverifiable in a shallow clone. | independent-thinker, critic | Replaced with PR numbers. |
| P1. The batch flipped ADR-042 but not six similar records, with no explanation. | independent-thinker | The asymmetry and its reason are now recorded in ADR-055's Status. |

## The corrected root cause, which the campaign originally got wrong

Issue #5199 diagnosed the `# ADR-032 Exception:` marker as "a renumbering pass applied with the wrong offset." That is wrong, and the first draft of ADR-055's repair repeated the error.

The marker was **correct when written**. This file was ADR-032. PR #1604 renamed the file and did not sweep the body. The number then silently came to mean `ADR-032-ears-requirements-syntax.md`.

The class is therefore **rename without in-body reference sweep**, and it recurs: ADR-033 links to a nonexistent `ADR-032-exit-code-standardization.md` from a 2025-12-31 numbering race that EARS won by 62 seconds. PR #1604's own remediation notes describe the sweep as a manual `git grep`. No gate checks that a record's self-references match its current number. `check_adr_uniqueness.py` enforces numeric uniqueness going forward only.

`check_adr_links.py`, shipped in this campaign, now catches the cross-record half through its `number-mismatch` rule. The self-reference half (a record citing its own former number in prose or a marker) is still ungated.

## Gate findings, dissent carried forward

The security reviewer proved two defects **in the commit gate that required this debate**, by execution in an isolated repository. Both are filed as issues and neither is resolved here.

- **The debate-log gate is forgeable.** `check_adr_review_policy` tests only that a staged file sits in `.agents/critique/`, ends in `.md`, has "debate" in its name, and matches `ADR-\d+` anywhere in its bytes. A 7-byte file cleared it. There is no verdict field, no roster, no round count, no tie to the record's content.
- **One-of-N authorization amplification.** `adr_ids` is the union of all staged ADR ids and the test is `any(...)`, so a log naming one record authorizes the whole staged set. This batch stages ten. A stub naming only ADR-042 cleared a commit that also modified an unrelated ADR.

This log was written to cover all ten records on their merits rather than to exploit that second defect, but the defect stands regardless of this batch's conduct.

The frontmatter-only exemption was tested and is **sound**: `status: proposed` to `accepted` with an unchanged body returns not-exempt and the gate blocks. The exemption set is `{"implemented"}` alone.

## Deferred, with dissent from the tie-breaker

Four deferrals the advisor judged decidable by evidence rather than owner taste: ADR-031 (`rejected`; zero PowerShell files under a Python-only mandate), ADR-028 (`deprecated`; an accepted rule governing an empty set), ADR-050 (its mandated script and the SESSION-PROTOCOL.md it synced were both deleted by PR #5179), and ADR-002 with ADR-039 (a provisional window expired 2026-01-17 whose policy is 0 for 6 in the running tree). Two deferrals judged genuine governance forks: ADR-052 versus ADR-036, and ADR-030's enum.

Recorded so the owner sees the split rather than a uniform "owner decision" label.
