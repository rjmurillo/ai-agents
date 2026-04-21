# Failure Pattern: Context Reading Failure

**Last Updated**: 2026-04-21
**Status**: active
**Severity**: High

## Summary

Agents begin work without reading required session-start context (HANDOFF.md, CLAUDE.md, AGENTS.md, steering docs). They rely on training priors or in-conversation memory instead of retrieval. Baseline non-compliance measured at 95.8% in December 2025 before verification gates were introduced.

## What Failed

- `2025-12-20-session-protocol-mass-failure.md`: 95.8% session-start non-compliance across sampled sessions. Serena init, memory search, and session log creation all skipped.
- `2025-12-17-protocol-compliance-failure.md`: Protocol files were present and discoverable, yet not referenced in the first 20 turns.

## What Worked

Verification-based BLOCKING gates produce an observable artifact:

- `SessionStart` hook prints the protocol reminder.
- `Validate-Session.ps1` checks required artifacts at session end.
- Pre-commit hook verifies the session log exists and is complete.

Trust-based instructions ("remember to read X") regress as context grows. Gates that emit an artifact tool can inspect do not.

## Current Recommendation

Never rely on prompt-based "please read" instructions. When a file MUST be read, back it with a hook or a pre-commit check that fails closed when the artifact is missing. Prefer adding a gate to adding a sentence.

## References

- `.agents/governance/FAILURE-MODES.md` Section 1
- ADR-007 Memory-First Architecture
- ADR-008 Protocol Automation via Lifecycle Hooks
- Retrospective: `.agents/retrospective/2025-12-20-session-protocol-mass-failure.md`
