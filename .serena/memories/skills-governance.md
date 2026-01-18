# Agent Governance Skills

**Extracted**: 2025-12-16
**Source**: `.agents/governance/` directory

## Skill-Governance-001: 8-Question Agent Interview (94%)

**Statement**: Validate agent design using 8 standardized questions

**Context**: Creating or reviewing agent definitions

**Evidence**: Agent interview protocol document with template

**Atomicity**: 94%

**Tag**: helpful

**Impact**: 9/10

**Questions**:

1. What is its purpose? (single sentence)
2. When should it be invoked? (entry criteria)
3. When is it done? (exit criteria)
4. What inputs does it need?
5. What outputs does it produce?
6. What tools does it require?
7. What constraints apply?
8. What are its handoffs?

**Source**: `.agents/governance/agent-interview-protocol.md`

---

## Skill-Governance-002: Five Consolidation Triggers (90%)

**Statement**: Merge agents when specific overlap/inefficiency patterns detected

**Context**: Quarterly agent review and maintenance

**Evidence**: Agent consolidation process document

**Atomicity**: 90%

**Tag**: helpful

**Impact**: 8/10

**Triggers**:
>
1. >50% output overlap between agents
2. Unclear routing decisions (orchestrator confusion)
3. Circular handoffs (A→B→A patterns)
4. Single-use agents (invoked once per quarter)
5. Excessive maintenance burden

**Source**: `.agents/governance/agent-consolidation-process.md`

---

## Related Documents

- Source: `.agents/governance/agent-interview-protocol.md`
- Source: `.agents/governance/agent-consolidation-process.md`
- Related: skills-design (agent design principles)
