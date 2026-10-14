---
source: wiki/concepts/Strategic Thinking/Systems Thinking.md
created: 2026-04-11
review-by: 2026-07-11
---

# Systems Thinking

## Principle

Understand behavior by examining the whole system, not isolated parts. System behavior emerges from the interactions between components, not from the components themselves.

## Core Concepts

| Concept | Definition | Example |
|---------|-----------|---------|
| Feedback loops | Output feeds back as input, amplifying or dampening | Team velocity drops, so management adds process, which drops velocity further |
| Emergence | System behavior not predictable from individual parts | Microservices that each work fine but create cascading failures together |
| Delays | Effects lag behind causes | Technical debt accrues silently, then explodes during a critical feature push |
| Leverage points | Small changes with outsized impact | Fixing a shared library bug vs patching each consumer |
| Mental models | Assumptions that shape how we interpret the system | "More engineers = faster delivery" (ignoring Brooks's Law) |

## Decision Critic Application

Use this model during **Challenge** (Steps 5-6) to identify second-order effects and feedback loops.

### Verification Questions

When evaluating any decision:

1. What feedback loops does this decision create or break?
2. What are the second-order effects? Third-order?
3. Where are the delays between action and consequence?
4. What leverage points exist? Are we acting on them or on symptoms?
5. What mental models are we assuming that might be wrong?

### Red Flags in Decisions

| Signal | Risk |
|--------|------|
| "This only affects component X" | Ignoring system interconnections |
| "We'll see results immediately" | Ignoring delays in the system |
| "More resources will fix it" | Linear thinking in a nonlinear system |
| "We fixed the symptom" | Root cause unaddressed, will resurface |
| Optimizing one metric aggressively | Goodhart's Law: metric becomes the target, not the goal |

### Second-Order Effect Analysis

For each proposed decision, trace effects through at least two levels:

```
Decision: [proposed action]
  -> First-order: [immediate, intended effect]
     -> Second-order: [downstream consequence]
        -> Third-order: [further ripple effect]
```

### Contrarian Perspectives (Step 5)

- "What if this fix creates a worse problem elsewhere in the system?"
- "What feedback loop are we accidentally creating?"
- "Are we treating the symptom or the cause?"
- "What will this look like in 6 months when delays manifest?"

### Failure Modes (for Inversion Analysis)

- Fixing a symptom while the root cause generates new symptoms
- Creating reinforcing feedback loops that accelerate problems
- Ignoring delays and declaring success before consequences arrive
- Optimizing a subsystem at the expense of the whole system
- Missing leverage points and applying effort where impact is lowest

## Practical Checklist

Before accepting a decision as VERIFIED:

- [ ] System boundaries defined (what is inside/outside scope)
- [ ] Feedback loops identified (reinforcing and balancing)
- [ ] Second-order effects traced for at least 2 levels
- [ ] Delays between action and effect estimated
- [ ] Leverage points identified and targeted
- [ ] Mental model assumptions stated explicitly

## Related Models

- Gall's Law: complex systems evolve from simple ones
- Chesterton's Fence: understand the system before changing it
- Survivorship Bias: examine the full system, not just visible outputs
