### 1A: Input Expansion

Transform user's goal into comprehensive requirements:

```
USER INPUT: "Create a skill for X"
                │
                ▼
┌─────────────────────────────────────────────────────────┐
│ EXPLICIT REQUIREMENTS                                    │
│ • What the user literally asked for                      │
│ • Direct functionality stated                            │
├─────────────────────────────────────────────────────────┤
│ IMPLICIT REQUIREMENTS                                    │
│ • What they probably expect but didn't say               │
│ • Standard quality expectations                          │
│ • Integration with existing patterns                     │
├─────────────────────────────────────────────────────────┤
│ UNKNOWN UNKNOWNS                                         │
│ • What they don't know they need                         │
│ • Expert-level considerations they'd miss                │
│ • Future needs they haven't anticipated                  │
├─────────────────────────────────────────────────────────┤
│ DOMAIN CONTEXT                                           │
│ • Related skills that exist                              │
│ • Patterns from similar skills                           │
│ • Lessons from skill failures                            │
└─────────────────────────────────────────────────────────┘
```

**Check for overlap with existing skills:**

```bash
ls ~/.claude/skills/
# Grep for similar triggers in existing SKILL.md files
```

| Match Score | Action |
|-------------|--------|
| >7/10 | Use existing skill instead |
| 5-7/10 | Clarify distinction before proceeding |
| <5/10 | Proceed with new skill |

### 1B: Multi-Lens Analysis

Apply all 11 thinking models systematically:

| Lens | Core Question | Application |
|------|---------------|-------------|
| **First Principles** | What's fundamentally needed? | Strip convention, find core |
| **Inversion** | What guarantees failure? | Build anti-patterns |
| **Second-Order** | What happens after the obvious? | Map downstream effects |
| **Pre-Mortem** | Why did this fail? | Proactive risk mitigation |
| **Systems Thinking** | How do parts interact? | Integration mapping |
| **Devil's Advocate** | Strongest counter-argument? | Challenge every decision |
| **Constraints** | What's truly fixed? | Separate real from assumed |
| **Pareto** | Which 20% delivers 80%? | Focus on high-value features |
| **Root Cause** | Why is this needed? (5 Whys) | Address cause not symptom |
| **Comparative** | How do options compare? | Weighted decision matrix |
| **Opportunity Cost** | What are we giving up? | Explicit trade-offs |

**Minimum requirement:** All 11 lenses scanned, at least 5 applied in depth.

See: [references/multi-lens-framework.md](references/multi-lens-framework.md)

### 1C: Regression Questioning

Iterative self-questioning until no new insights emerge:

```
ROUND N:
│
├── "What am I missing?"
├── "What would an expert in {domain} add?"
├── "What would make this fail?"
├── "What will this look like in 2 years?"
├── "What's the weakest part of this design?"
└── "Which thinking model haven't I applied?"
    │
    └── New insights > 0?
        │
        ├── YES → Incorporate and loop
        └── NO → Check termination criteria
```

**Termination Criteria:**

- Three consecutive rounds produce no new insights
- All 11 thinking models have been applied
- At least 3 simulated expert perspectives considered
- Evolution/timelessness explicitly evaluated
- Automation opportunities identified

See: [references/regression-questions.md](references/regression-questions.md)

### 1D: Automation Analysis

Identify opportunities for scripts that enable agentic operation:

```
FOR EACH operation in the skill:
│
├── Is this operation repeatable?
│   └── YES → Consider generation script
│
├── Does this produce verifiable output?
│   └── YES → Consider validation script
│
├── Does this need state across sessions?
│   └── YES → Consider state management script
│
├── Does this involve external tools?
│   └── YES → Consider integration script
│
└── Can Claude verify success autonomously?
    └── NO → Add self-verification script
```

**Automation Lens Questions:**

| Question | Script Category if YES |
|----------|----------------------|
| What operations will be repeated identically? | Generation |
| What outputs require validation? | Validation |
| What state needs to persist? | State Management |
| Can the skill run overnight autonomously? | All categories |
| How will Claude verify correct execution? | Verification |

**Decision: Script vs No Script**

| Create Script When | Skip Script When |
|-------------------|------------------|
| Operation is deterministic | Requires human judgment |
| Output can be validated | One-time setup |
| Will be reused across invocations | Simple text output |
| Enables autonomous operation | No verification needed |
| External tool integration | Pure Claude reasoning |

See: [references/script-integration-framework.md](references/script-integration-framework.md)
