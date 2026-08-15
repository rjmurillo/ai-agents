---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-14711-b79742bf0-draft-adr-094-proposing-scoped-re-review.json
qaCommit: fa39b0200c8cdb8b9e1a56a38bfc9a15c42377b0
---

# QA: ADR-094 draft (session 14711)

## Why this report exists separately

Session 14711 drafted ADR-094. Session 99916 then triaged the PR #5062 review
threads and rewrote parts of the draft, and
`.agents/qa/qa-adr-094-scoped-re-review-axes.md` records that second session's
work: its "Correction found and applied" section is about the 72% to 53%
arithmetic fix that 99916 made, not about the draft as first written.

Both logs pointed at that one report. A QA report binds to exactly one session
log (`.claude/lib/qa_report.py` `validate_qa_report`), so the shared claim made
session 14711's validation fail with "QA report session log does not match
current session", which is one of the two red session-log checks that were
already on PR #5062 before the adr-review debate ran. This report gives session
14711 its own binding and states what that session actually verified.

## Scope

One added file at the time: `.agents/architecture/ADR-095-scoped-re-review-axes.md` (drafted as ADR-094),
a `status: proposed` ADR draft. No code, no generated artifact, no shipped skill
change.

## What that session verified

| Check | Result |
|---|---|
| Em-dash and en-dash prohibition (`.claude/rules/universal.md` MUST NOT 5) | 0 and 0 |
| Frontmatter `status` is a valid ADR-073 enum value | `proposed` |
| Cited file and line references resolve | Verified at draft time |
| Markdown lint | PASS |

## Superseded by later sessions

Three of that session's conclusions did not survive later review and are
recorded here so this report is not read as still certifying them.

- The draft's 72% reduction figure was arithmetic that omitted the always-on
  Stage-1 axis and the initial full run. Session 99916 corrected it to 53%.
- Eight further defects in the draft were found by the PR #5062 review threads
  and fixed in `e699ab744` and `e2b2c7ba3`.
- The adr-review debate at `.agents/critique/ADR-094-debate-log.md` records five
  P0 findings against the draft, including that its three cost incidents predate
  the mechanism the ADR proposes to change. The debate verdict is NOT ACCEPTED,
  narrow and re-measure.

## Not verified

- **The draft's cost model.** No scoped mode exists, so the reduction figure is
  arithmetic on an assumed workload in every version of this document. The
  debate log records that the workload parameter itself is unmeasured.
- **Whether the ADR should be accepted.** That is the maintainer's decision on
  the debate evidence. This report covers text-rule conformance and citation
  resolution only.

## Verdict

PASS on the scope this session owned: the draft conformed to the repository's
text rules and its citations resolved when written. It is not a verdict on the
decision the ADR proposes.
