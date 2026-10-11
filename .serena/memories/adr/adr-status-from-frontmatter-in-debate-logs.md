# Skill: Copy ADR status from frontmatter into debate logs (100%)

**Atomicity Score**: 100%
**Source**: Retrospective `.project-toolkit/retrospective/2026-10-11-goal-followup-loop.md`
**Date**: 2026-10-11
**Tag**: harmful (the failure this prevents)
**Impact**: 6/10 (a wrong lifecycle state in a review record)

## Statement

Copy ADR status from frontmatter into debate logs; #6274 misstated ADR-114 as accepted.

## Evidence

The #6274 debate log said ADR-097, ADR-101, ADR-109 and ADR-114 "stay accepted". ADR-114's frontmatter says `status: proposed`. Three of the four were accepted, and the summary generalized from them. Devin flagged it, and commit a79216aa6 fixed it. Check with `grep -m1 '^status:'` on each edited ADR before writing a Final Status line.
