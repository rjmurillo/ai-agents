---
applyTo: docs/retros/**
---

# Retrospective File Rules

Retrospectives exist so the same failure does not happen twice. They feed future governance and instruction changes, so the format matters.

## When To Write One

Event-triggered, never scheduled. Write a retrospective when one of these fires:

1. A defect, incident, or rollback reached `main` or CI.
2. A pull request closed unmerged, carried a rework marker, or drew heavy review friction. The Post-PR Retrospective workflow raises this one on PR close and skips bot and fork pull requests.
3. A gate, hook, or validator misfired: blocked correct work, or passed work it should have blocked.
4. A session burned significant time on a failure mode already in `.agents/governance/FAILURE-MODES.md`, or on one that belongs there and is missing.
5. Someone asks for one.

A day on which none of those fired needs no retrospective. A pre-push gate used to demand one per calendar day or per session; it was removed because the artifact it produced on a quiet day recorded nothing and cost every push. A retro written to satisfy a counter is worse than no retro: it dilutes the corpus that `retrospective` and the failure canon read.

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
- `.github/workflows/post-pr-retrospective.yml`. The PR-close trigger
- `.agents/retrospective/`. Historical examples
