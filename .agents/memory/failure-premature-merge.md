# Failure Pattern: Premature Merge and Deploy

**Last Updated**: 2026-04-21
**Status**: active
**Severity**: Critical

## Summary

PRs merged before required checks completed, before review threads resolved, or before human review when policy required it. Recovery involves reverts, stakeholder apologies, and audit debt. Automation convenience tempts agents to skip gates.

## What Failed

- `2025-12-22-pr-226-premature-merge-failure.md`: PR merged while checks were still yellow. Downstream deploy broke. Revert + postmortem required.
- Auto-merge enabled on PRs without required checks configured, so auto-merge fired on the first passing check of any kind.

## What Worked

- Branch protection with required status checks (not optional).
- Auto-merge relies on required checks; never merges until they pass.
- PR readiness validator blocks merge when review threads remain unresolved.
- Explicit human-review label for changes touching security, governance, or ADRs.

## Current Recommendation

Treat auto-merge as "merge once every required gate is green", not "merge now". If a check is optional in Actions but required in policy, promote it to required. If a review must be human, label the PR and let the gate hold.

## References

- `.agents/governance/FAILURE-MODES.md` Section 5
- ADR-026 PR Automation Concurrency and Safety
- `.claude/skills/validate-pr-description/`
- Retrospective: `.agents/retrospective/2025-12-22-pr-226-premature-merge-failure.md`
