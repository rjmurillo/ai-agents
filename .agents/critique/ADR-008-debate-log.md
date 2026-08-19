# ADR Debate Log: ADR-008 Protocol Automation via Lifecycle Hooks

## Summary

- **Scope**: correction only. The Context Loader hook (`invoke_context_loader.py`)
  stopped auto-injecting `.agents/HANDOFF.md` in PR #5170 (issue #5168); ADR-008's
  Implementation Status and Acceptance Criteria Mapping tables still claimed the
  old behavior as currently true. A Copilot review comment on PR #5170 flagged the
  contradiction. No architecture, policy, or decision content changed.
- **Rounds**: 1
- **Outcome**: Consensus (5 Accept, 1 Disagree-and-Commit, reservation incorporated)
- **Final Status**: accepted (unchanged; this is a correction to an already-accepted ADR, not a status transition)

## Round 1 Summary

### Key Issues Addressed

- The proposed row (first draft) *replaced* the original "as accepted" Evidence
  text with the narrowed description, which independent-thinker identified as
  contradicting this table's own stated purpose (rows preserve the original
  claim; drift is recorded separately). Fixed by restoring the original Evidence
  text and moving the narrowing note to the status column and a new amendment
  section, mirroring the existing `#3184`/`#3349` treatment.
- critic flagged that the Implementation Status table (line 131) would still
  read bare `Implemented` while the Acceptance Criteria table recorded drift,
  recreating the two-tables-disagree problem the 2026-07-26 amendment fixed.
  Fixed by adding `, narrowed by #5170` to that row, matching the sibling row's
  `Implemented, trimmed by #3273` format.
- architect and independent-thinker both caught a pre-existing, unrelated typo
  in the same paragraph being edited ("As accepted in 2026" vs. the ADR's actual
  2025-12-20 acceptance date). Fixed in the same pass since it sits inside the
  paragraph under edit.

### Major Changes Made

- `Implementation Status` table, Context Loader row: `Implemented` →
  `Implemented, narrowed by #5170`.
- New `### Amendment 2026-08-19 (Issue #5168, PR #5170)` section added, mirroring
  the existing `### Amendment 2026-07-26 (Issue #3373)` section's role: records
  what changed and why without rewriting the original decision.
- `Acceptance Criteria Mapping` table, "SessionStart loads context" row: Evidence
  restored to the original `Auto-injects HANDOFF.md + latest retro`; status
  column changed from `Yes` to `Partially, HANDOFF.md dropped by #5168/#5170`.
- Fixed `As accepted in 2026` → `As accepted 2025-12-20` (pre-existing error,
  same paragraph).

### Agent Positions

| Agent | Position | Notes |
|-------|----------|-------|
| architect | Accept | Confirmed structural compliance with the table's own drift-recording convention; flagged the 2026/2025-12-20 date typo (P2, incorporated) and an Evidence/status symmetry nit (P2, incorporated via the independent-thinker fix) |
| critic | Accept | Verified hook docstring matches the new claim; flagged Implementation Status row 131 inconsistency (P2, incorporated) and that no test gate checks Evidence-column content (P2, noted as follow-up, not blocking) |
| independent-thinker | Disagree-and-Commit → resolved | P1: first-draft edit overwrote as-accepted Evidence text against the table's own stated purpose. Restructure proposed (restore Evidence, move drift to status column, add amendment row) was incorporated; would now Accept on the revised text |
| security | Accept | No security-relevant surface in a documentation-table correction; dropping HANDOFF.md auto-load reduces untrusted-content-in-context surface rather than expanding it |
| analyst | Accept | Independently verified all four factual claims (hook diff, HANDOFF.md banner/content, ADR-014's existence and purpose, the pre-existing "No, retired by #NNNN" convention) against the actual files rather than trusting the prompt |
| high-level-advisor | Accept | Judged the six-agent process disproportionate for a one-cell factual correction (P0 priority but trivial cost); recommended a follow-up issue on adr-review triage by severity, separate from this fix |

### Next Steps

- Follow-up issue (not filed as part of this correction): adr-review has no
  severity triage. A pure factual correction to an existing table cell
  triggers the same six-agent, Phase-0-through-4 process as a new architectural
  decision. high-level-advisor's assessment: "This debate cost more than the
  fix." Worth a lightweight-correction path that still produces an auditable
  record without the full debate.
- critic's noted gap (no test asserts Evidence-column content, only
  hook-file-existence) is a real but separate hardening task, not blocking this
  correction.
