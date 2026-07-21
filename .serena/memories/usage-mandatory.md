# Skill-First: Incident Log

The skill-first rule itself is canonical in [`AGENTS.md`](../../AGENTS.md) ("Skill-First" section, "Never: Raw gh when skills exist") and [`CLAUDE.md`](../../CLAUDE.md) ("Skill routing"). A `invoke_skill_first_guard.py` PreToolUse hook previously enforced it, but ADR-085 (#3217) retired that hook: it self-neutered outside this repo and Copilot CLI ignores repo-committed permission surfaces, so it enforced only Claude sessions in ai-agents and shipped dead to every consumer. The rule is now advisory, carried by the canonical prose above. This memory keeps only the episodic incidents that motivated the rule.

## PR Review Comment Routing (session 1187, 2026-02-08)

**Specific failure mode**: PR review comments with CWE-* bypassed security-scan skill

**User correction**: "just use the security-scan skill to fix these"

- Context: 12 bot comments about CWE-22 path traversal
- What happened: Manual path validation instead of running security-scan
- Why it matters: Skills encode validated patterns; manual fixes led to linting iterations

**Checkpoint**: Before responding to security bot comments, ask:
"Is this a CWE-* pattern? If yes, route to security-scan skill"

## Memory Alone Is Insufficient (PR #226)

An agent read this memory and then violated it with raw `gh` commands in the same session. Reading guidance does not enforce it. At the time, the `invoke_skill_first_guard` hook was the enforcement layer; ADR-085 later retired that hook, so the rule is now advisory only. Treat prose rules without hooks as advisory.

## Pre-PR Validation (Issue #934, PR #908)

Before creating any PR, verify no BLOCKING synthesis issues exist (check synthesis panel documents for `blocking: true`). User rejects PRs with unresolved BLOCKING synthesis issues.
