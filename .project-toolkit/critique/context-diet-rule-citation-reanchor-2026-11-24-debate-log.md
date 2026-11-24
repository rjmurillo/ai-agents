# ADR Debate Log: re-anchor ADR citations of rules moved by the context diet

## Summary

- **Rounds**: 5 of 10 (round 5 was critic only)
- **Outcome**: Consensus
- **Final Status**: unchanged (the edit changes no ADR status or decision)
- **Scope**: citations of three moved rules in ADR-062, ADR-071, ADR-096, ADR-100, ADR-102,
  ADR-103, ADR-107, and ADR-109. The rules are lsp-first, generated-artifacts, and
  ci-scripts.
- **Panel**: reduced panel, architect and critic. The edit changes citations only. No
  enforcement logic changes.
- **Gate scope**: only lines the gates read were changed. `check_adr_lifecycle.py`
  cited-paths-exist reads Decision and Implementation Notes. The ADR-107 conformance test
  reads its gate table. Older paths elsewhere were left on purpose.

The diet first moved or dropped 26 rules. An eval then showed 11 moves lose capability when
routed. Richard narrowed the change on 2026-11-24. Seventeen rules were restored. Eight
moved into skill references: ci-scripts, lossless-queue-reads, lsp-first,
generated-artifacts, efficiency, code-quality, powershell, and csharp. token-economy was
dropped. Base: `84c395f822`.

The moves are not all verbatim. Each reference drops frontmatter and gains a header comment
and portability markers. `rule-generated-artifacts.md` MUST 2 is now a pointer to the
repo-local `ai-agents-validation-and-qa` skill, which owns the full text.

## Method

- A moved rule's citation reads "the former `X` rule (now at `<successor path>`)". The
  sentence stays historical and the path resolves.
- A sentence that describes the old file, such as its instruction mirrors, keeps that
  meaning because it names the former rule.

## Round 1 Summary

Scope at the time: all 26 changed rules across 15 ADRs.

### Key Issues Addressed

- ADR-109 anchors pointed at the wrong successor line. A sibling citation was missed.
- ADR-062 line 295 claimed the successor file had instruction mirrors.
- Dropped-rule wording used the present tense.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Block. Wrong ADR-109 anchors and a missed line. |
| critic | Block. Same findings, plus tense and one historical pattern. |

## Round 2 Summary

### Major Changes Made

- One pattern for every moved rule: "the former `X` rule (now at ...)".
- Historical ADR-109 citations kept their old path with reasoned ignore markers.
- Tense and capitals fixed.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept. |
| critic | Accept. |

## Round 3 Summary

### Key Issues Addressed

- The ADR-107 C6 conformance row cited the deleted generated-artifacts rule. It now names
  the former rule and its successor.
- Pre-existing error, not changed: the row credits MUST 2 with a gate over the committed
  artifact. That has always been MUST 3. The PR body flags it for the owner.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept. Citation-only. |
| critic | Accept. Record the MUST 3 mislabel for the owner. |

## Round 4 Summary

The scope narrowed to three moved rules. Every earlier edit for a restored rule was
reverted to the base text, including the ADR-109 markers and line renumbering. The revert
returns ADR-083, ADR-084, ADR-092, ADR-093, ADR-097, ADR-101, and ADR-108 to their base
text, along with the architecture README row for ADR-093.

### Key Issues Addressed

- No half-reverted lines remain. The net diff against the base touches 8 files and 13
  lines, all for lsp-first, generated-artifacts, or ci-scripts.
- ADR-062 lines 294 to 295 broke a sentence ("One canonical rule The former ..."). It now
  reads "One canonical rule, the former `lsp-first` rule (now at ...), mirrored to ...".
  The original path stays out of a code span because the line is in the Decision section.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept. All 13 lines are citation-only and true. |
| critic | Block on the ADR-062 sentence, then accept once it was fixed. |

## Round 5 Summary

### Key Issues Addressed

- The added-lines citation check also scans unchanged lines near an edit. ADR-102 line 327
  sits two lines above an edited line. Its bare `:160-168` was written for the resolver path,
  but the checker binds it to `TESTING-RIGOR.md`, the last path on the line.
- The line gains a reasoned `citation-freshness: ignore` marker. Its text is unchanged.
- Line 325, also near the edit, cites `.claude/lib/qa_report.py:173-177` as the code stood
  when the ADR was written. It gets the same kind of marker.

### Agent Positions

| Agent | Position |
|-------|----------|
| critic | Accept. Keep historical numbers with reasoned markers, as the 2026-11-20 precedent did. |

## Final Verdicts

| Agent | Verdict |
|-------|---------|
| architect | ACCEPT |
| critic | ACCEPT |

## Gate Evidence

- `check_adr_lifecycle.py`: cited-paths-exist at 57/57, at baseline.
- `tests/validation/test_adr107_conformance_gates.py`: 24 passed.
- `citation_reverse_pass.py`: passes at `c06b7c100e` (returns True).
- `check_citation_freshness.py`: passes at `c06b7c100e`, 8 citations examined.
