# ADR-035 Amendment Debate Log: Hook Exit Code Semantics

**Date**: 2026-02-07
**Amendment**: Add per-hook-type exit code semantics to Claude Code Hook Exit Codes section
**Trigger**: Session fix for SessionStart hooks incorrectly using exit 2

## Amendment Summary

Updated ADR-035 "Claude Code Hook Exit Codes" section to accurately categorize
which hook types support exit 2 blocking and which do not. Previous version
only mentioned PreToolUse and UserPromptSubmit. Updated version includes the
complete list from Claude Code documentation.

## Agent Verdicts

| Agent | Verdict | Confidence | Key Finding |
|-------|---------|------------|-------------|
| architect | ACCEPT | High | Accurate, maintains ADR coherence |
| critic | ACCEPT | 95% | Factually accurate, no issues |
| security | ACCEPT | High | Risk 1/10, no security controls weakened |
| independent-thinker | DISAGREE-AND-COMMIT | High | Table was incomplete (missing blocking hooks) |
| analyst | PASS | High | Research confirms amendment is justified |
| high-level-advisor | ACCEPT | High | Documentation correction, no status change needed |

**Consensus**: 5 ACCEPT + 1 DISAGREE-AND-COMMIT = CONSENSUS REACHED

## Independent-Thinker D&C Resolution

**Issue raised**: The original amendment's table grouped Stop/SubagentStop as
non-blocking, but Claude Code docs show they DO support exit 2 blocking.
PermissionRequest, TeammateIdle, and TaskCompleted also support blocking.

**Resolution**: Table updated to include complete blocking/non-blocking
categorization from Claude Code documentation:

- **Blocking**: PreToolUse, PermissionRequest, UserPromptSubmit, Stop,
  SubagentStop, TeammateIdle, TaskCompleted
- **Non-blocking**: PostToolUse, PostToolUseFailure, Notification,
  SubagentStart, SessionStart, SessionEnd, PreCompact

**Dissent recorded**: The independent-thinker's feedback was incorporated
into the final amendment before commit.

## P0/P1 Issues

None identified. All agents agreed this is a documentation correction.

## Recommendations

No further action required. The amendment corrects inaccurate documentation
and aligns with the official Claude Code hooks reference.
