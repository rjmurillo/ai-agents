# Failure Pattern: Trust-Based Compliance Degradation

**Last Updated**: 2026-04-21
**Status**: active
**Severity**: High

## Summary

Instructions that ask an agent to "remember", "verify", "double-check", or "make sure" without producing an inspectable artifact degrade as context grows. Compliance starts above 90% early in the session and drops below 50% after compaction or long task chains. The fix is the same every time: replace trust with a verification gate.

## What Failed

- Retrospectives across December 2025 through January 2026 repeatedly document the same shape: a soft requirement, a predictable lapse, no feedback loop.
- Prompt-based gates survived one or two sessions, then quietly regressed.

## What Worked

- BLOCKING gates that emit an artifact: hook output, validator exit code, file presence check, structured session log field.
- MUST language paired with an enforcement mechanism (not MUST language alone).
- Clear consequence on failure: commit blocked, PR blocked, session cannot close.

## Current Recommendation

Before writing a new "please do X" instruction, ask:

1. What artifact will show X was done?
2. What tool can inspect the artifact?
3. What fails closed when the artifact is missing?

If any answer is "none", the instruction will not hold. Add the gate first, then document it.

## References

- `.agents/governance/FAILURE-MODES.md` Cross-Cutting Theme
- `.agents/governance/PROTOCOL-ANTIPATTERNS.md`
- ADR-008 Protocol Automation via Lifecycle Hooks
- Forgetful memory: "Trust-Based Compliance Failure (<50% vs 100%)"
