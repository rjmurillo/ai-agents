# Critique Skills

**Extracted**: 2025-12-16
**Source**: `.agents/critique/` directory

## Skill-Critique-001: Conflict Escalation Protocol (90%)

**Statement**: When specialists disagree, document positions and escalate to high-level-advisor

**Context**: Multi-agent decision conflicts and disagreements

**Evidence**: Agent templating critique identified specialist disagreement pattern

**Atomicity**: 90%

**Tag**: helpful

**Impact**: 8/10

**Protocol**:

1. Document each specialist's position clearly
2. Note areas of agreement vs. disagreement
3. Identify decision criteria that differ
4. Escalate to high-level-advisor with all positions
5. Apply disagree-and-commit after decision

**Anti-Pattern**:

- Stalling on consensus
- Overriding specialist without escalation
- Endless debate without resolution

**Source**: `.agents/critique/001-agent-templating-critique.md`

---

## Related Documents

- Source: `.agents/critique/001-agent-templating-critique.md`
- Related: skills-workflow (handoff patterns)
