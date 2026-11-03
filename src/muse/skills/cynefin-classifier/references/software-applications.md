# Cynefin in Software Engineering

Practical applications of the Cynefin Framework for software development teams.

## Domain Patterns by Activity

### Requirements and Planning

| Situation | Domain | Approach |
|-----------|--------|----------|
| Well-understood feature request | Clear | Estimate and schedule |
| Feature with technical uncertainty | Complicated | Spike first, then estimate |
| Novel product area | Complex | Prototype, get feedback |
| Regulatory emergency | Chaotic | Comply first, optimize later |
| Vague stakeholder request | Confusion | Discovery session |

### Architecture and Design

| Situation | Domain | Approach |
|-----------|--------|----------|
| Adding endpoint to existing API | Clear | Follow existing patterns |
| Scaling a bottleneck | Complicated | Profile, analyze, optimize |
| Microservices vs monolith | Complex | Build both small-scale, measure |
| Major incident during design | Chaotic | Defer design, stabilize |
| "Should we use X?" (new tech) | Complex | Spike with real use case |

### Development and Debugging

| Situation | Domain | Approach |
|-----------|--------|----------|
| Fixing typo | Clear | Fix and ship |
| Memory leak | Complicated | Profile, analyze, fix |
| Flaky tests | Complex | Instrument, experiment, observe |
| Production down | Chaotic | Rollback, restore, investigate |
| "Something is wrong but..." | Confusion | Add observability |

### Testing

| Situation | Domain | Approach |
|-----------|--------|----------|
| Unit tests for pure functions | Clear | Write tests, meet coverage |
| Integration test strategy | Complicated | Analyze dependencies, design |
| User acceptance criteria | Complex | Iterative feedback |
| Security testing after breach | Chaotic | Immediate pen test |
| "How much testing is enough?" | Confusion | Analyze risk, decide |

### Operations

| Situation | Domain | Approach |
|-----------|--------|----------|
| Deploying with CI/CD | Clear | Follow pipeline |
| Capacity planning | Complicated | Analyze trends, model |
| User behavior prediction | Complex | A/B test, measure |
| DDoS attack in progress | Chaotic | Mitigate, then investigate |
| "Is the system healthy?" | Confusion | Improve observability |

## Common Misclassifications

### Architecture Decisions as Complicated

**Mistake**: "Let's analyze React vs Vue thoroughly before deciding."

**Reality**: Team dynamics, learning curves, ecosystem evolution are emergent. This is Complex.

**Better**: Build small prototypes with each. Measure team velocity and satisfaction. Let experience inform the decision.

### Debugging as Clear

**Mistake**: "This is just a bug. Apply the fix pattern."

**Reality**: Many bugs require investigation to understand root cause. This is Complicated.

**Better**: Gather data, analyze systematically, then apply targeted fix.

### Flaky Tests as Complicated

**Mistake**: "Let's debug this test systematically."

**Reality**: Flaky tests often involve timing, concurrency, environment factors that interact unpredictably. This is Complex.

**Better**: Add instrumentation, run experiments, look for patterns, amplify stability.

### Outages as Complex

**Mistake**: "Let's understand the root cause before taking action."

**Reality**: Active outage with user impact is Chaotic. No time for analysis.

**Better**: Execute runbook, restore service, then investigate.

## Decision Trees

### "How Should We Approach This Bug?"

```text
Is production down / users blocked?
├── Yes → CHAOTIC: Stabilize first
└── No → Can we reproduce?
    ├── No → CONFUSION: Gather more data
    └── Yes → Have we seen this pattern before?
        ├── Yes, documented fix exists → CLEAR: Apply fix
        └── No → COMPLICATED: Investigate root cause
```

### "How Should We Make This Technical Decision?"

```text
Is there immediate harm occurring?
├── Yes → CHAOTIC: Act to stop harm
└── No → Is there a documented best practice?
    ├── Yes, context matches → CLEAR: Apply practice
    └── No → Can an expert analyze options?
        ├── Yes, predictable outcomes → COMPLICATED: Analyze
        └── No, emergent factors → COMPLEX: Experiment
```

### "How Should We Handle This User Request?"

```text
Is the request clear and well-defined?
├── No → CONFUSION: Clarify requirements
└── Yes → Have we built this before?
    ├── Yes, identical → CLEAR: Reuse
    ├── Yes, similar → COMPLICATED: Adapt
    └── No, novel → COMPLEX: Prototype
```

## Team Practices by Domain

### For Clear Problems

- Standardize solutions in runbooks
- Automate repetitive tasks
- Train junior developers to handle
- Monitor for deviation from expected

### For Complicated Problems

- Maintain expert knowledge base
- Regular knowledge sharing sessions
- Pair programming with experts
- Document analysis and solutions

### For Complex Problems

- Create safe-to-fail experiment culture
- Short feedback loops
- Retrospectives to capture patterns
- Tolerance for "productive failure"

### For Chaotic Problems

- Runbooks for crisis response
- Clear escalation paths
- Regular fire drills
- Post-incident reviews

## Metrics by Domain

### Clear Domain Metrics

- Time to resolution (should be fast and consistent)
- Automation rate
- Junior dev self-service rate

### Complicated Domain Metrics

- Expert utilization
- Analysis accuracy
- Knowledge documentation rate

### Complex Domain Metrics

- Experiment velocity
- Learning rate (patterns discovered)
- Pivot frequency

### Chaotic Domain Metrics

- Mean time to stabilize
- Runbook coverage
- Escalation effectiveness

## Integration with Agile

| Agile Concept | Cynefin Application |
|---------------|---------------------|
| Sprint Planning | Classify stories by domain |
| Story Points | Higher for Complex (uncertainty premium) |
| Spikes | Explicitly for Complex domain items |
| Retros | Capture domain transitions |
| Definition of Done | Varies by domain |

### Story Classification

Add Cynefin domain to story cards:

```text
[STORY] Add pagination to user list
Domain: CLEAR
Approach: Apply standard pagination pattern
```

```text
[STORY] Improve search relevance
Domain: COMPLEX
Approach: A/B test ranking algorithms
```

```text
[SPIKE] Evaluate GraphQL adoption
Domain: COMPLEX
Approach: Build prototype, measure developer experience
```
