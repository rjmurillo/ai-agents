---
paths:
  - ".project-toolkit/retrospective/**"
  - "docs/retros/**"
priority: normal
---

# Retrospective File Rules

Retrospectives exist so the same failure does not happen twice. They feed future governance and instruction changes, so the format matters.

## When To Write One

Event-triggered, never scheduled. Four triggers warrant a full retrospective:

1. A `reflect` pass produced a HIGH-confidence finding.
2. `main` went red.
3. A merge was reverted or force-fixed.
4. The user corrected the work explicitly.

One more fires on its own: the Post-PR Retrospective workflow runs on PR close, and escalates depth for an unmerged close, a rework marker in the title, or heavy review comment density. It skips bot and fork pull requests.

A day on which none of those fired owes no retrospective. A pre-push gate used to demand one per calendar day or per session; it was removed because the artifact it produced on a quiet day recorded nothing and cost every push. A retro written to satisfy a counter is worse than no retro: it dilutes the corpus the failure canon and the `retrospective` skill read.

## MUST

1. **Filename convention**. New retros MUST use `YYYY-MM-DD-<slug>.md` (e.g., `2026-04-21-instruction-files-rollout.md`).
2. **Failure mode classification**. Each retro MUST classify the failure against `.agents/governance/FAILURE-MODES.md`. If no existing class matches, MUST propose a new class in a linked ADR.
3. **Evidence**. MUST include links to the offending commits, PRs, issues, or CI runs. No hand-waving.
4. **Remediation**. MUST list concrete follow-up actions (governance change, ADR, instruction update, skill change) with owners or issues.
5. **No blame**. MUST critique processes and artifacts, never individuals.

## SHOULD

1. **Impact table**. SHOULD include an `Impact` table with severity (High / Medium / Low) per affected area.
2. **Root cause**. SHOULD apply the five-whys or timeline analysis and write the root cause explicitly.
3. **Learning capture**. SHOULD use the `reflect` skill to extract patterns and persist HIGH-confidence learnings to Serena memory.

## MUST NOT

1. MUST NOT delete or edit landed retros to soften criticism. Corrections append a new section with a date and rationale.
2. MUST NOT ship remediation commits without linking the retro in the commit body or PR.

## References

- `.agents/governance/FAILURE-MODES.md`. Failure mode taxonomy
- `.claude/skills/reflect/SKILL.md`. Learning-capture workflow
- `.claude/skills/retro/`. On-demand retrospective skill (if present)
- `.project-toolkit/retrospective/`. Historical examples
