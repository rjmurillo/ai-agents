# Agent Design Principles

## Purpose

These principles guide the design, implementation, and evolution of agents in the multi-agent system. All agents must adhere to these principles, and new agent proposals are evaluated against them.

---

## Principle 1: Non-Overlapping Specialization

**Statement**: Each agent has a unique specialty that does not substantially overlap with other agents.

### Requirements

- Maximum 20% capability overlap with any other agent
- Clear differentiation in primary function
- No duplicate capabilities without explicit reason

### How to Verify

1. Complete overlap analysis in ADR
2. Map capabilities to existing agents
3. Calculate overlap percentage
4. Document differentiation

### Example: Good

```text
security agent:     Vulnerability detection, threat modeling
implementer agent:  Code writing, test creation

Overlap: 0% - Security identifies, Implementer fixes
```

### Example: Bad

```text
code-reviewer agent:  Code review, quality checks
qa agent:             Quality checks, code review

Overlap: 70% - Both do code quality
Solution: Merge or differentiate clearly
```

---

## Principle 2: Clear Entry Criteria

**Statement**: Developers can determine "Should I use this agent?" in under 30 seconds.

### Requirements

- Objective, measurable criteria (not subjective)
- Pattern-based triggers when possible
- Documented in agent definition and interview

### How to Verify

1. Write entry criteria as if/then statements
2. Test with 5 sample tasks
3. Time how long decision takes
4. Refine until < 30 seconds

### Example: Good

```text
Use security agent when:
- Files match: **/Auth/**, **/Security/**, .githooks/*
- Task mentions: vulnerability, CVE, threat, security
- Risk level: High or Critical
```

### Example: Bad

```text
Use security agent when:
- You think there might be security concerns
- It seems like a security task
- You're worried about security
```

---

## Principle 3: Explicit Limitations

**Statement**: Every agent clearly documents what it CANNOT do.

### Requirements

- Limitations section in agent definition
- Technical limitations (languages, frameworks)
- Scope limitations (what's out of scope)
- Dependency limitations (what requires other agents)
- Output limitations (what can't be produced)

### How to Verify

1. Test edge cases
2. Document failures
3. Update limitations from real-world usage
4. Include in interview protocol responses

### Example: Good

```text
Security Agent Limitations:
- CANNOT run dynamic analysis (penetration testing)
- CANNOT access production systems
- CANNOT implement fixes (handoff to implementer)
- CANNOT validate runtime behavior
- CANNOT perform compliance audits (SOC2, HIPAA)
```

### Example: Bad

```text
Security Agent Limitations:
- Some things might not work perfectly
- Not suitable for all security tasks
```

---

## Principle 4: Composability

**Statement**: Agents can work together in sequences without modification.

### Requirements

- Standard input format (task description)
- Standard output format (structured deliverable)
- Clear handoff artifacts
- No hidden dependencies

### How to Verify

1. Test in 3+ different agent chains
2. Verify outputs are consumable by next agent
3. Document pairing preferences
4. Ensure no agent-specific coupling

### Example: Good

```text
analyst -> architect -> implementer -> qa

Each agent:
- Receives structured task
- Produces documented artifact
- Hands off with clear summary
```

### Example: Bad

```text
analyst -> custom-bridge -> architect

Requires custom adapter between agents
Breaks if bridge agent unavailable
```

---

## Principle 5: Verifiable Success

**Statement**: Agent success is measurable against defined criteria.

### Requirements

- Quantifiable success metrics
- Clear acceptance criteria per task type
- Testable outcomes
- Baseline measurements

### How to Verify

1. Define metrics in agent interview
2. Establish baselines
3. Track outcomes
4. Review quarterly

### Example: Good

```text
Security Agent Metrics:
- Vulnerabilities detected per review: Target 95% of known
- False positive rate: < 10%
- Time to complete review: < 2 hours
- CWE coverage: OWASP Top 10 + CWE-78, 79, 89
```

### Example: Bad

```text
Security Agent Metrics:
- Does good security reviews
- Catches most issues
- Usually helpful
```

---

## Principle 6: Consistent Interface

**Statement**: All agents follow the same input/output contract.

### Requirements

- Documented input format
- Documented output location
- Consistent naming conventions
- Predictable behavior

### Input Contract

```markdown
## Task for [Agent Name]

**Objective**: [What to accomplish]
**Scope**: [What to analyze/work on]
**Context**: [Relevant background]
**Constraints**: [Time, priority, limitations]
**Expected Output**: [What to deliver]
```

### Output Contract

```markdown
## [Agent Name] Report: [Topic]

**Summary**: [1-2 sentences]

**Findings/Results**: [Detailed output]

**Recommendations**: [If applicable]

**Handoff**: [Next agent or completion]
```

### How to Verify

1. Review agent definitions for consistency
2. Test input parsing
3. Validate output format
4. Update interview protocol

---

## Principle Compliance Matrix

| Agent | Non-Overlap | Entry Criteria | Limitations | Composable | Verifiable | Consistent |
|-------|-------------|----------------|-------------|------------|------------|------------|
| analyst | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| architect | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| security | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| implementer | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| ... | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |

*Update this matrix during quarterly reviews*

---

## Enforcement

### New Agent Proposals

All ADRs must demonstrate compliance with all 6 principles:

- [ ] Overlap analysis < 20%
- [ ] Entry criteria objective and testable
- [ ] Limitations explicitly documented
- [ ] Tested in agent chains
- [ ] Success metrics defined
- [ ] Input/output format documented

### Existing Agents

- Quarterly review for principle drift
- Interview protocol re-run annually
- Non-compliant agents flagged for remediation

### Violations

| Severity | Definition | Action |
|----------|------------|--------|
| Minor | Single principle partial non-compliance | Document, fix in next update |
| Major | Multiple principles non-compliant | Remediation plan required |
| Critical | Fundamental design violation | Consolidation or retirement |

---

## Related Documents

- [ADR Template](../architecture/ADR-TEMPLATE.md)
- [Steering Committee Charter](./steering-committee-charter.md)
- [Agent Consolidation Process](./agent-consolidation-process.md)
- [Agent Interview Protocol](./agent-interview-protocol.md)

---

*Principles Version: 1.0*
*Established: 2025-12-13*
*GitHub Issue: #8*
