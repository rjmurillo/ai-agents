---
source: wiki/concepts/Critical Thinking/Falsifiability.md
created: 2026-05-31
review-by: 2026-08-31
---

# Falsifiability

## Principle

A claim is meaningful only if there is some observation that could prove it false. A claim that no possible evidence could refute is not a strong claim, it is an unfalsifiable one.

> "A theory which is not refutable by any conceivable event is non-scientific." -- Karl Popper

## Classic Example

"This design is more maintainable" is unfalsifiable until you name the measure: time to add a feature, defect rate per change, lines touched per change. With a measure attached, the claim can be tested and can fail. Without one, it can never be wrong, which means it can never be right either.

## Decision Critic Application

Use this model during **Verification** (Steps 3-4) to test whether each claim has a defined success criterion. Apply it whenever a claim is asserted without a measurable way to tell if it is wrong.

### Verification Questions

When a decision asserts a benefit or an outcome:

1. What observation would prove this claim false?
2. Is there a measurable success criterion, or only a direction ("better", "cleaner", "faster")?
3. Who measures it, when, and against what baseline?
4. If the claim cannot fail, why are we treating it as evidence?

### Red Flags in Decisions

| Signal | Risk |
|--------|------|
| "This will improve quality" | No metric; cannot be shown false |
| "Users will love it" | No measurable acceptance criterion |
| "This is the right architecture" | Aesthetic claim dressed as a testable one |
| "It scales better" | No load number, no threshold, no test |
| "We will know it when we see it" | Success defined after the fact, never disprovable |

### Falsification Test

For each asserted benefit, write the disproof condition before the work starts:

```
Claim: [asserted benefit]
  Measure: [the metric that captures it]
  Baseline: [current value]
  Success threshold: [value that would confirm the claim]
  Failure condition: [observation that would prove the claim false]
```

If you cannot fill the failure condition line, the claim is not yet evidence. Treat it as UNCERTAIN, not VERIFIED.

### Contrarian Perspectives (Step 5)

- "What result would make us admit this decision was wrong?"
- "Is this claim testable, or is it immune to any evidence?"
- "What is the number, the baseline, and the threshold?"

### Failure Modes (for Inversion Analysis)

- Accepting an unfalsifiable benefit as if it were measured fact
- Declaring success against a goal defined only after the outcome is known
- Investing in a change whose value can never be confirmed or denied
- Confusing a confident assertion with a tested one

## Practical Checklist

Before accepting an asserted benefit as VERIFIED:

- [ ] A measurable success criterion is named
- [ ] A baseline value exists or is estimated
- [ ] A failure condition is written before the work starts
- [ ] The owner and timing of the measurement are defined

## Related Models

- Survivorship Bias: a falsifiable claim still needs the full population to test honestly
- Brandolini's Law: a falsifiable claim is cheaper to refute than a vague one
- Systems Thinking: define the boundary and the metric before claiming improvement
