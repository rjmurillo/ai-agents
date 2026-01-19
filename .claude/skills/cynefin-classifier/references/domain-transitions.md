# Cynefin Domain Transitions

Understanding how problems move between domains helps predict when to shift approaches.

## Natural Evolution (Clockwise)

### Chaotic to Complex

**When**: Initial crisis stabilized, basic functionality restored.

**Signal**: "We stopped the bleeding, now what?"

**Action**: Shift from pure action to structured experimentation.

**Software Example**:

- Production outage resolved
- Now investigating root cause with safe probes
- Running diagnostics that might reveal patterns

### Complex to Complicated

**When**: Patterns have emerged through experimentation.

**Signal**: "We've seen this pattern three times now."

**Action**: Bring in experts to formalize understanding.

**Software Example**:

- A/B tests revealed clear user preference
- Now can analyze why systematically
- Expert review to codify learnings

### Complicated to Clear

**When**: Expert knowledge has been documented and validated.

**Signal**: "We've created a runbook for this."

**Action**: Train broader team, automate where possible.

**Software Example**:

- Debugging process documented
- Checklist created for similar issues
- Junior developers can now handle

## Disruption (Counter-Clockwise)

### Clear to Complicated

**When**: Context changes invalidate existing best practices.

**Signal**: "The standard approach isn't working anymore."

**Action**: Re-engage experts, analyze what changed.

**Software Example**:

- New dependency breaks established build process
- Previous "clear" CI configuration now fails
- Need expert analysis of new requirements

### Complicated to Complex

**When**: Analysis reveals emergent or unpredictable factors.

**Signal**: "Every time we think we understand, something new emerges."

**Action**: Switch from analysis to experimentation.

**Software Example**:

- Performance optimization reveals cascading effects
- Each fix creates new unexpected behavior
- Need to probe and observe, not analyze

### Any Domain to Chaotic

**When**: Black swan event, unexpected crisis.

**Signal**: "Everything is on fire."

**Action**: Immediate stabilization, defer all analysis.

**Software Example**:

- Security breach detected
- Data corruption in progress
- All other work stops, stabilize first

## The Cliff Edge

The most dangerous transition is **Clear to Chaotic** without warning.

### How It Happens

1. Organization treats Clear problems as permanently solved
2. No questioning of assumptions
3. No adaptation to changing context
4. Sudden failure when context shifts dramatically

### Symptoms Before the Fall

- "We've always done it this way"
- Dismissing anomalies as noise
- Over-confidence in automation
- No recent stress testing

### Prevention

- Regular challenge of "best practices"
- Planned chaos engineering
- Cross-training to prevent knowledge silos
- Periodic audits of assumptions

## Detecting Transitions

### Early Warning Signs

| Current Domain | Transition Signal | Likely Destination |
|----------------|-------------------|-------------------|
| Clear | Anomalies increasing | Complicated |
| Complicated | Analysis yielding contradictions | Complex |
| Complex | Patterns stabilizing | Complicated |
| Chaotic | Order emerging | Complex |
| Confusion | Information gathered | Any |

### Questions to Ask

1. **Has context changed recently?** (technology, team, requirements)
2. **Are established approaches still working?**
3. **Are we seeing unexpected outcomes?**
4. **Do experts still agree on approach?**

## Software Engineering Transitions

### Typical Project Lifecycle

```text
Project Start (Complex)
    ↓ prototypes reveal patterns
Architecture Phase (Complicated)
    ↓ decisions codified
Implementation (Clear)
    ↓ unexpected issues
Debugging (Complicated)
    ↓ crisis detected
Incident Response (Chaotic)
    ↓ stabilized
Post-Mortem (Complex → Complicated)
    ↓ improvements codified
Operations (Clear)
```

### Team Lifecycle

```text
New Team (Complex)
    ↓ processes emerge
Performing Team (Complicated)
    ↓ practices standardized
Mature Team (Clear)
    ↓ member turnover / scaling
Reforming Team (Complex)
```

## Action Checklists

### When Entering Complex from Chaotic

- [ ] Document what actions stabilized the situation
- [ ] Identify remaining unknowns
- [ ] Design safe-to-fail probes
- [ ] Set up feedback loops

### When Entering Complicated from Complex

- [ ] Document observed patterns
- [ ] Identify expert resources
- [ ] Define analysis approach
- [ ] Set deadline for decision

### When Entering Clear from Complicated

- [ ] Create documentation/runbook
- [ ] Train broader team
- [ ] Identify automation opportunities
- [ ] Schedule periodic review
