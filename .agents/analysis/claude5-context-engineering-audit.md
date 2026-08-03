# Claude 5 Context-Engineering Audit

**Issue**: #4321
**Date**: 2026-08-02
**Auditor**: ctxaudit agent (fix/ctxaudit-agent-context)
**Source**: Anthropic blog post "The new rules of context engineering for Claude 5 generation models" (2026-07-24, Thariq Shihipar)

## Scope

This audit covers six areas from issue #4321. Three are confirmed compliant at the measured commit (5ee7a95d5). One is partially measured. Two are deferred as out of scope for a single-session pass.

## Always-on token budget

Root `AGENTS.md`: 2,991 bytes. Root `CLAUDE.md`: 2,482 bytes. Combined: 5,473 bytes. The issue baseline said 5,467 bytes; the 6-byte delta is immaterial. The repo's root always-on surface is already lean.

## Area 1: Retired myth "Give Claude rules vs. Let Claude use judgment"

**Status: Compliant.**

The `Never:` line in root `AGENTS.md` (line 27) reads:

```
Commit secrets|Edit HANDOFF.md|New bash scripts|Logic in YAML (ADR-006)|Raw gh if skill exists|Force push|Skip hooks|Internal refs in src|Scratch in tree|Resolve security threads w/o fix|Ship unrun gen artifact
```

Each item has a concrete operational justification:

| Item | Justification | Keep |
|------|--------------|------|
| Commit secrets | Irreversible data exposure | Yes |
| Edit HANDOFF.md | ADR-014 read-only contract | Yes |
| New bash scripts | ADR-042 Python-first policy | Yes |
| Logic in YAML | ADR-006 separation | Yes |
| Raw gh if skill exists | Usage-mandatory contract | Yes |
| Force push | Shared branch integrity | Yes |
| Skip hooks | Bypasses validation gates | Yes |
| Internal refs in src | Plugin self-containment (REQ-003) | Yes |
| Scratch in tree | Prevents untracked noise in repo | Yes |
| Resolve security threads w/o fix | Security thread closure policy | Yes |
| Ship unrun gen artifact | Validation gate | Yes |

The issue flagged "Use bash" and "Scratch in tree" as potential style calls. PR #4185 already tightened "Use bash" to "New bash scripts," binding it to ADR-042. "Scratch in tree" prevents agents from creating untracked files in the worktree. Both items are safety rails, not style calls.

**Finding**: No change needed.

## Area 2: Retired myth "Give Claude examples vs. Design interfaces"

**Status: Deferred.**

Auditing 98 skills for example-heavy definitions is a multi-session effort. Out of scope for this audit. Filed as follow-up in the PR body.

## Area 3: Conflicting instructions across layers

**Status: Partially measured.**

Root-level always-on layers (root `AGENTS.md`, root `CLAUDE.md`, `.agents/AGENTS.md`) were read. No contradictions found. Root `CLAUDE.md` imports `AGENTS.md` with `@AGENTS.md` rather than inlining, which prevents drift.

The full 70-file corpus was not audited for cross-layer conflicts. This is the highest-priority deferred item, because the Anthropic post identifies it as a common failure mode.

**Finding**: Root layer clean. Full audit deferred.

## Area 4: More literal instruction following

**Status: Deferred.** Out of scope for this session.

## Area 5: Code review harness recall

**Status: Compliant.**

The 12 review axis prompts under `.claude/skills/review/references/` and their generated mirrors under `.github/prompts/pr-quality-gate-*.md` were examined. None use severity-suppressing language. Each axis reports all findings with severity and determines verdict from the highest-severity finding. This matches the Anthropic recommendation to split coverage from filtering.

**Finding**: No change needed.

## Area 6: Self-verification directives for older models

**Status: Compliant.**

All agent files under `.claude/agents/` were searched for self-verification patterns. No matches. The orchestrator's "Verify artifacts, not reports" directive is a delegation guard (check subagent artifacts), not a self-audit loop, and should stay.

**Finding**: No change needed.

## What this audit did not cover

- Area 2: Example-heavy skill descriptions (98 skills, multi-session pass)
- Area 3: Full 70-file cross-layer conflict audit
- Area 4: Scope literalness of individual rules
- Anthropic `/doctor` command: requires Claude Code harness with doctor tool

## Recommended follow-on

File a separate issue for a systematic cross-layer conflict audit (Area 3). Compare the always-on layer against the 25 path-scoped rules. This is the highest-value target from the Anthropic guidance.
