---
name: reflect
version: 1.0.0
model: claude-sonnet-4-6
description: CRITICAL learning capture. Extracts HIGH/MED/LOW confidence patterns from conversations to prevent repeating mistakes and preserve what works. Use PROACTIVELY after user corrections ("no", "wrong"), after praise ("perfect", "exactly"), when discovering edge cases, or when skills are heavily used. Without reflection, valuable learnings are LOST forever. Acts as continuous improvement engine for all skills. Invoke EARLY and OFTEN - every correction is a learning opportunity.
license: MIT
metadata:
  timelessness: 8/10
  adr: ADR-007, ADR-017
---

# Reflect Skill

**Critical learning capture system** that prevents repeating mistakes and preserves successful patterns across sessions.

Analyze the current conversation and propose improvements to skill-based memories based on what worked, what didn't, and edge cases discovered. **Every correction is a learning opportunity** - invoke proactively to build institutional knowledge.

---

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `reflect on this session` | Extract learnings from conversation |
| `learn from this mistake` | Capture correction patterns |
| `capture what we learned` | Document session insights |
| `improve skill {name}` | Target specific skill memory |
| `what did we learn` | Review and store patterns |

Three priority tiers drive invocation timing: HIGH (corrections, invoke
immediately), MEDIUM (praise, edge cases, invoke after multiple), LOW
(repeated patterns, invoke at session end). Invoke proactively, not only on
explicit request: a user "no" or "perfect" is a HIGH signal.

See [references/triggers.md](references/triggers.md) for the full priority-tiered
trigger tables, the original trigger phrases, and the proactive-invocation
reminder.

---

## When to Use

Use this skill when:

- User corrects your output ("no", "wrong", "not like that")
- User praises specific output ("perfect", "exactly")
- Edge cases are discovered during work
- Session end after skill-heavy work
- Want to capture learnings before they are lost

Use [retrospective](../retrospective/SKILL.md) instead when:

- Conducting a full session retrospective (broader scope)
- Analyzing multi-session patterns across the project

---

## Process

### Phase 1: Identify the Target Skill

Locate the skill-based memory to update:

1. **Check Serena memories**: Look for files ending with `-observations.md` in `.serena/memories/`
2. **Infer from context**: Identify which skill(s) were used in the conversation
3. **Create if needed**: If missing, propose `{skill-name}-observations.md` (skill observations pattern)

**Storage Locations**:

- **Serena MCP (canonical)**: `.serena/memories/{skill-name}-observations.md` via `mcp__serena__write_memory`
- **Contingency (Serena unavailable)**: Manually edit the same file in Git and note the manual update in the session log for later Serena sync

### Phase 2: Analyze the Conversation

Scan the conversation for learning signals at four confidence levels: HIGH
(corrections), MEDIUM (success patterns, edge cases), and LOW (preferences).
Only propose changes when the confidence threshold is met (>=1 HIGH, >=2 MED,
or >=3 LOW signals).

See [references/phase2-signal-detection.md](references/phase2-signal-detection.md)
for the full detection patterns per confidence level and the threshold table.

### Phase 3: Propose Learnings

Present findings in a confidence-labeled summary ([HIGH]/[MED]/[LOW] with the
source quote for each), then await user approval (`Y`/`n`/`edit`). **Always
show changes before applying.**

### Phase 4: Persist Learnings to Memory

After approval: read existing memory, append new learnings with timestamp and
session reference, preserve existing content, extract code citations, and write
to `.serena/memories/{skill-name}-observations.md` (Serena MCP canonical; Git
fallback when Serena is unavailable).

See [references/phase3-4-propose-persist.md](references/phase3-4-propose-persist.md)
for the proposal display format, user-response handling, persistence strategy,
memory format, and the Phase 4 auto-citation capture.

---

## Decision Tree, Examples, and Anti-Patterns

See [references/decision-tree-and-examples.md](references/decision-tree-and-examples.md)
for the full invocation decision tree, worked examples (correction, success
pattern, edge case), per-domain use cases (code review, API design, testing,
documentation), and the anti-patterns table.

---

## Integration, Design Decisions, and Commit Convention

See [references/integration-and-design.md](references/integration-and-design.md)
for integration with the session protocol, the memory skill, and Serena; the
design-decision rationale (sidecar naming, Serena vs Forgetful roles,
relationship to `curating-memories`); extension points; and the commit
convention for skill observation updates.

---

## Verification

| Action | Verification |
|--------|--------------|
| Analysis complete | Signals categorized by confidence |
| User approved | Explicit Y or approval statement |
| Memory updated | File written to `.serena/memories/` |
| Changes preserved | Existing content not lost |
| Commit ready | Changes staged, message drafted |

---

## Related

| Skill | Relationship |
|-------|--------------|
| `memory` | Skill memories are part of Tier 1 |
| `using-forgetful-memory` | Alternative storage for skill learnings |
| `curating-memories` | For maintaining/pruning skill memories |
| `retrospective` | Full session retrospective (this is mini version) |
