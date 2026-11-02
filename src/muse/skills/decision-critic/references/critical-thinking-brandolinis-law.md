---
source: wiki/concepts/Critical Thinking/Brandolinis Law.md
created: 2026-05-31
review-by: 2026-08-31
---

# Brandolini's Law

## Principle

The energy needed to refute a claim is an order of magnitude larger than the energy needed to produce it.

> "The amount of energy needed to refute bullshit is an order of magnitude bigger than that needed to produce it." -- Alberto Brandolini

Also called the bullshit asymmetry principle. A confident, unsupported claim is cheap to write and expensive to disprove. The asymmetry favors the producer, so unverified claims accumulate faster than reviewers can clear them.

## Decision Critic Application

Use this model during **Verification** (Steps 3-4) to allocate scrutiny, and during **Challenge** (Steps 5-6) to budget review effort. Apply it to review-burden allocation: flag any claim whose refutation effort exceeds its authorship effort.

### Verification Questions

When a decision rests on assertions that are cheap to state:

1. How much effort did this claim cost to produce versus to verify?
2. Did the author supply the evidence, or is the burden of disproof shifted to the reviewer?
3. Are unsupported claims accumulating faster than they can be checked?
4. Which claims carry the most consequence if accepted on faith?

### Red Flags in Decisions

| Signal | Risk |
|--------|------|
| "It is obvious that..." | Burden shifted to the reviewer; no evidence supplied |
| A wall of confident assertions, no citations | Refutation cost dwarfs authorship cost |
| "Trust me, this is faster" | Claim cheap to make, expensive to disprove |
| Many small claims, each plausible | Aggregate verification cost exceeds review budget |
| "Prove me wrong" | Asymmetry weaponized; producer pays nothing |

### Review Burden Allocation

For each claim in the decision, estimate the asymmetry:

```
Claim: [assertion]
  Authorship effort: [low | medium | high]
  Refutation effort: [low | medium | high]
  If refutation > authorship: require the author to supply evidence first
```

Do not spend reviewer energy chasing a claim the author can support cheaply. Push the evidence burden back to the producer when the asymmetry is steep.

### Contrarian Perspectives (Step 5)

- "Whose job is it to disprove this, and is that a fair use of review effort?"
- "What single piece of evidence would let me stop refuting this by hand?"
- "Are we losing the review on volume of claims rather than on merit?"

### Failure Modes (for Inversion Analysis)

- Reviewers exhausted by refutation, so a weak decision passes by attrition
- Burden of proof silently inverted: the author asserts, the reviewer disproves
- High-consequence claims accepted because checking each one was too costly
- Review velocity collapses as unsupported claims accumulate

## Practical Checklist

Before accepting a claim-heavy decision as VERIFIED:

- [ ] High-consequence claims carry author-supplied evidence
- [ ] Refutation effort budgeted only where it is cheaper than demanding evidence
- [ ] Burden of proof sits with the producer, not the reviewer
- [ ] No decision passes purely because refuting it was too expensive

## Related Models

- Survivorship Bias: missing data inflates the cost of honest verification
- Falsifiability: a claim with a clear disproof test is cheaper to refute
- Systems Thinking: review burden is a flow; unbounded claims overflow it
