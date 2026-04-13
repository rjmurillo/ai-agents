# Skill Sidecar Learnings: Retrospective

**Last Updated**: 2026-01-21
**Sessions Analyzed**: 3

## Constraints (HIGH confidence)

- Prioritize failure case retrospectives over success stories - failures contain more actionable HIGH confidence learnings (Session 07, 2026-01-16)
  - Evidence: Analysis of 26 retrospectives showed failure cases (session-protocol-mass-failure with 95.8% failure rate, PR-211-security-miss with 2-day vulnerability window) yielded blocking enforcement and QA gate patterns, while success stories provided fewer actionable constraints

## Preferences (MED confidence)

- Batch 15-25 learnings before /reflect invocation to reduce tool overhead while maintaining focus (Session 07, 2026-01-16)
  - Evidence: First batch persistence of 21 learnings across 7 observation files completed efficiently without context loss

- Apply atomicity scoring to each learning: 70%+ = extractable skill, 85%+ = HIGH confidence (Session 07, 2026-01-16)
  - Evidence: Consistently applied threshold across all retrospective analysis with scores ranging 78-98%, provides objective quality measure

- Cross-reference skill domains when analyzing retrospectives - single file often yields learnings for 3-5 different skill areas (Session 07, 2026-01-16)
  - Evidence: PR-715-phase2 retrospective yielded security (path traversal), PowerShell (array efficiency), testing (non-numeric IDs), documentation (Mermaid diagrams) patterns from one 998-line file

- Implementation summary as retrospective artifact pattern - create IMPLEMENTATION-SUMMARY-{feature}.md files as lightweight alternative to full retrospective agent invocation (Session 68, 2025-12-22)
  - Evidence: Session 68 guardrails implementation used IMPLEMENTATION-SUMMARY-guardrails.md as retrospectiveInvoked evidence, capturing outcomes without invoking retrospective agent
- User feedback critical for analysis depth - initial analysis may miss learnings until user requests deeper extraction (Session 07, 2026-01-16)
  - Evidence: Batch 37 - Initial 41 learnings expanded to 91 after user feedback requesting more thorough analysis
- Iterative reflection more accurate than batch - invoke /reflect per skill domain for better learning extraction (Session 07, 2026-01-16)
  - Evidence: Batch 37 - Domain-specific reflection invocations yielded higher quality learnings than bulk processing

- Use Five Whys analysis for root cause discovery in failure retrospectives (PR #908, 2026-01-15)
  - Evidence: PR #908 retrospective used 5 distinct Five Whys analyses reaching true root causes (governance, feedback loop, ADR exceptions, scope, security)
  - Template: Problem → Q1/A1 → Q2/A2 → Q3/A3 → Q4/A4 → Q5/A5 → Root Cause → Actionable Fix
  - Reference: Issue #940 (retrospective templates)

- Use Fishbone analysis for cross-category pattern identification (PR #908, 2026-01-15)
  - Evidence: Categories (Prompt, Tools, Context, Dependencies, Sequence, State) revealed lack of enforcement, late feedback, scope management patterns
  - Template: Pre-define categories, identify controllable vs uncontrollable factors
  - Reference: Issue #940 (retrospective templates)

- Use Force Field analysis to quantify driving vs restraining forces (PR #908, 2026-01-15)
  - Evidence: Quantified restraining forces (25) vs driving forces (14) explaining why scope explosion persists
  - Template: List forces with weights (1-5), calculate totals, identify highest-weight interventions
  - Reference: Issue #940 (retrospective templates)

- Automated PR failure analyzer as tooling recommendation for data gathering (PR #908, 2026-01-15)
  - Evidence: Manual counting of 228+ comments, 59 commits, 95 files took longer than analysis itself
  - Actionable: Create script that extracts metrics (commits, files, comments, reviews) and generates initial data gathering section
  - Reference: Issue #940 (retrospective tooling)

## Edge Cases (MED confidence)

- None yet

## Notes for Review (LOW confidence)

- None yet

## Related

- [retrospective-001-pr-learning-extraction](retrospective-001-pr-learning-extraction.md)
- [retrospective-001-recursive-extraction](retrospective-001-recursive-extraction.md)
- [retrospective-002-retrospective-to-skill-pipeline](retrospective-002-retrospective-to-skill-pipeline.md)
- [retrospective-003-token-impact-documentation](retrospective-003-token-impact-documentation.md)
- [retrospective-004-evidence-based-validation](retrospective-004-evidence-based-validation.md)
- PR #908 retrospective - Case study for Five Whys, Fishbone, Force Field templates
