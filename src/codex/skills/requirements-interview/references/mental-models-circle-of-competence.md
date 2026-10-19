---
source: wiki/concepts/Mental Models/Circle of Competence.md
created: 2026-06-03
review-by: 2026-09-03
---

# Circle of Competence

## Principle

Your circle of competence is the domain where your knowledge is deep enough, tested enough, and current enough that your judgment is reliable. Everything outside the circle sits between "educated guess" and "you do not know what you do not know." The model, popularized by Buffett and Munger and codified in Parrish's The Great Mental Models Vol. 1, has two operating rules:

1. Make high-stakes decisions inside the circle. That is where your edge is.
2. Know when you have stepped outside it. The circle is small; the failure mode is not noticing the boundary.

> "Part of successfully using circles of competence includes knowing when we are outside them." Parrish

The circle is dynamic. Knowledge decays: what you knew about a framework two versions ago is partly wrong now. A circle that is not actively maintained shrinks even when it feels stable. The hidden cost of seniority is that the longer you have been in a role, the more your circle is remembered rather than tested.

## Requirements Interview Application

Use this lens during the interview to calibrate how hard to push on a recommended answer and how much verification to demand before a decision is CONFIRMED. The skill already says "if the codebase can answer it, answer it" and "recommend an answer for every question." Circle of Competence tells you when the recommendation is trustworthy and when it needs evidence behind it.

### Calibration Questions

For each branch in the design tree, ask where the answer sits relative to the circle:

1. Is this decision inside a domain the team genuinely knows cold, or one it only feels familiar with?
2. Did the recommended answer come from a tested source (a code path, an ADR, a measured benchmark), or from a remembered assumption?
3. If the decision is outside the circle, what raises the verification: a spike, a specialist, a primary-source read, before the answer is CONFIRMED?
4. Is the boundary of the circle being noticed, or is overconfidence treating an outside-the-circle guess as an inside-the-circle fact?

### Effect on Question Discipline

- **Inside the circle:** the recommended answer can carry the decision. Cite the source, confirm ownership, close the branch.
- **At the edge:** lower action confidence. Mark the answer `DEFERRED` pending a spike, or demand a primary-source citation before `CONFIRMED`.
- **Outside the circle:** the honest recommendation is "we do not know this yet." Promote it to a spike, delegate to a specialist, or flag it as an open question. Do not let a confident-sounding guess masquerade as a settled requirement.

### Red Flags in an Interview

| Signal | Risk |
|--------|------|
| Confident answer with no citable source | A remembered assumption presented as tested knowledge |
| "We have always done it this way" | Circle remembered, not retested; the ground may have shifted |
| Decision in a new domain answered as fast as a familiar one | Boundary of the circle not noticed |
| Junior asked to own a decision outside their circle | Sets up blame for a call they were not equipped to make |

## Operating Moves

- **Map the circle explicitly.** Separate what the team knows cold from what it feels it knows. The gap is where overconfidence lives.
- **Outside the circle, raise verification.** Spike, ask, or delegate to a specialist before committing. An outside-the-circle decision needs evidence, not confidence.
- **Match direction to the circle.** When someone is operating outside their competence, the answer is high direction and support, not pretending they are inside it.

## Practical Checklist

Before marking an interview decision CONFIRMED:

- [ ] Located the decision relative to the team's circle of competence
- [ ] Confirmed the recommended answer rests on a tested source, not a remembered assumption
- [ ] For outside-the-circle decisions, raised verification (spike, specialist, primary source) before confirming
- [ ] Noticed and named the boundary where confidence outran knowledge

## Related Models

- Falsifiability: an outside-the-circle claim still needs a measurable success criterion.
- Chesterton's Fence: understand an existing constraint before deciding it no longer applies.
- Survivorship Bias: a remembered "this always works" may be selecting on the cases that survived.

## Sources

- Parrish and Beaubien, The Great Mental Models Vol. 1, ch. 2.
- Originates with Warren Buffett (Berkshire shareholder letters).
