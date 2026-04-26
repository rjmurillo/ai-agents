# Negotiation Agent Skills

Category: Deal Intelligence and Offer Analysis

## Skill-Negotiation-001: Always Quantify the Value Gap

- **Statement**: Never describe an offer as "acceptable" or "fair" without first quantifying what value remains uncaptured. State the gap in dollar terms.
- **Context**: Any offer analysis (real estate, compensation, vendor, resource allocation).
- **Atomicity**: 95%
- **Evidence**: Anthropic Project Deal (Dec 2025). Opus agents extracted $2 to $4 more per item than Haiku agents. Participants with weaker agents rated satisfaction identically despite objectively worse outcomes. The gap is invisible without explicit quantification.
- **Impact**: Prevents accepting sub-optimal deals that feel satisfactory
- **Tags**: negotiation, value-gap, deal-intelligence

**Implementation**:
```
INVISIBLE DISADVANTAGE CHECK:
  Offer net value: $[X]
  Achievable value: $[Y]
  Gap: $[Z] ([%])
  Reasoning: [specific market data, comps, or leverage]
```

---

## Skill-Negotiation-002: RADAR Protocol Sequence

- **Statement**: Every negotiation analysis follows Read, Analyze, Design, Assess, Review in sequence. Never skip steps.
- **Context**: Any offer evaluation requiring a counter-proposal
- **Atomicity**: 88%
- **Evidence**: Consistent application of structured analysis prevents anchoring to the other party's frame before establishing your own ZOPA.
- **Impact**: Prevents reactive countering from the wrong anchor
- **Tags**: negotiation, protocol, analysis

**Step sequence**:
1. Read: extract every term; identify anchors, hedging, urgency signals, omissions
2. Analyze: ZOPA, BATNA, information asymmetry, value gap
3. Design: PCP framing (Perception, Context, Permission) before counter
4. Assess: invisible disadvantage check; risk of countering vs. accepting
5. Review: DRAFT output with approval gate

---

## Skill-Negotiation-003: PCP Framing Before Anchoring

- **Statement**: Apply Perception, Context, Permission framing before presenting any counter number. Whoever defines the frame controls the negotiation.
- **Context**: Drafting counter-proposals
- **Atomicity**: 85%
- **Evidence**: Chase Hughes PCP model. Frame-setting is the highest-leverage move in any negotiation. The first number anchors the entire conversation.
- **Impact**: Reduces anchoring to the other party's number; increases acceptance rate of counter
- **Tags**: negotiation, influence, framing, PCP

**Pattern**:
- Perception: "This isn't [their framing], it's [your framing]."
- Context: "Market data, comps, or precedent shows [your anchor is normal]."
- Permission: "If you can do X, we can do Y." Give them a path to yes.

---

## Skill-Negotiation-004: Time Control

- **Statement**: Do not match urgency you did not create. Set your own cadence. Use silence after a counter.
- **Context**: Any negotiation with deadline pressure from the other party
- **Atomicity**: 82%
- **Evidence**: Navarro: "Whoever controls time, controls." Urgency pressure is the most common manipulation pattern. False deadlines dissolve when tested.
- **Impact**: Prevents concession under artificial pressure
- **Tags**: negotiation, time-control, pressure-tactics

**Test for genuine vs. tactical urgency**:
- Genuine: the deadline has a concrete external cause (closing date, board meeting, offer expiry)
- Tactical: the deadline serves only the other party's interest with no external anchor
- Response to tactical urgency: slow down, become methodical, request justification

---

## Skill-Negotiation-005: Bundle; Never Trade One Dimension

- **Statement**: When multiple terms are open, trade them as a package. Never concede one item in isolation.
- **Context**: Multi-term negotiations (real estate, comp, vendor contracts)
- **Atomicity**: 90%
- **Evidence**: Single-dimension concessions deplete leverage item by item. Bundling creates the perception of reciprocity while protecting total value.
- **Impact**: Preserves total deal value across all terms
- **Tags**: negotiation, bundling, concessions

**Pattern**:
- Identify all open dimensions (price, timeline, contingencies, concessions)
- When conceding on one: "We can do [X on dimension A] if you can do [Y on dimension B]"
- Never say "we can reduce the price" without extracting something in return

---

## Skill-Negotiation-006: Model Tier Routing for Negotiation Tasks

- **Statement**: Route negotiation analysis and counter-drafting to senior-tier models. Never route to junior.
- **Context**: Any agentic system where negotiation analysis is delegated
- **Atomicity**: 93%
- **Evidence**: Anthropic Project Deal (Dec 2025): model capability gap produced $2.68 more per item as seller, $2.45 less as buyer. Prompting style (aggressive vs. friendly) had no statistically significant effect. Only model capability mattered.
- **Impact**: Approximately 13% better outcome per item vs. weaker model
- **Tags**: negotiation, model-routing, agent-design, capability-tiers

**Routing rule**:
```yaml
task: negotiation-analysis
minimum_tier: senior
rationale: >
  Negotiation requires multi-step reasoning across ZOPA/BATNA,
  behavioral signal detection, and frame design. Junior models
  leave measurable value on the table without the loss being
  detectable to the human.
```

---

## Skill-Negotiation-007: Written Communication Signals

- **Statement**: Detect comfort/discomfort signals in written offers using adapted Navarro framework. Text has equivalent signals to nonverbal behavior.
- **Context**: Analyzing written offers, email threads, term sheets
- **Atomicity**: 78%
- **Evidence**: Navarro's comfort/discomfort binary applies to written communication via language patterns: hedging = flexibility, formality shift = discomfort, unprompted alternatives = weak BATNA.
- **Impact**: Surfaces hidden leverage without face-to-face interaction
- **Tags**: negotiation, behavioral-reading, written-signals

**Signal table**:

| Text Signal | Likely Meaning | Response |
|-------------|---------------|----------|
| Short clipped sentences | Power play or impatience | Slow down, add detail |
| Excessive qualifiers (just, maybe) | Insecurity, flexibility | Push harder here |
| Urgency framing (need answer by) | Pressure tactic OR genuine | Verify; do not match urgency |
| Matching your language/tone | Rapport building | Good sign, maintain |
| Shift to formal tone mid-thread | Discomfort, pulling back | Create safety |
| Unprompted alternatives listed | Weak BATNA | They need this deal more than stated |
| "Final offer" early | Anchoring attempt | Test with a counter |
| Long explanation for small ask | Guilt about ask | The ask is negotiable |

---

## Skill-Negotiation-008: Anchor First Only With Information Advantage

- **Statement**: Anchor first only when you have better data than the other party. Otherwise let them go first and use their anchor as information.
- **Context**: Any negotiation where the price or terms are not pre-set. Open offers, counter-offers, term sheet drafts.
- **Atomicity**: 86%
- **Evidence**: Anchoring research (Galinsky, Chen, Mussweiler) shows the first offer pulls the final price toward it. The exception: when you have information disadvantage, anchoring locks you to your wrong belief. Letting the other party anchor reveals their reservation point and leverage.
- **Impact**: Prevents leaving value on the table from low anchors. Prevents revealing weakness from high anchors without supporting data.
- **Tags**: negotiation, anchoring, information-asymmetry

**Decision rule**:
- You have better market data: anchor first, justify with data.
- They have better data: ask for their position first, then counter from your ZOPA, not their anchor.
- Information symmetric: anchor first if your ZOPA is wider than theirs, since you can move further without breaking.

---

## Skill-Negotiation-009: BATNA Discipline; Pre-Commit the Walkaway

- **Statement**: Define your walkaway price and conditions before negotiation starts. Write them down. Do not adjust mid-negotiation under emotional pressure.
- **Context**: Any negotiation where you have an actual alternative (other offers, status quo, no-deal option).
- **Atomicity**: 92%
- **Evidence**: Fisher and Ury (Getting to Yes). Negotiators who pre-commit to a written BATNA close at better prices and walk away cleanly when the deal is below their reservation point. Negotiators who set BATNA mid-conversation drift upward under sunk-cost pressure.
- **Impact**: Prevents accepting deals worse than your no-deal option. Prevents prolonged negotiation theater after the ZOPA has closed.
- **Tags**: negotiation, BATNA, walkaway, pre-commitment

**Pre-commitment artifact**:
```
BATNA WORKSHEET (complete before first counter):
  Walkaway price: $[X]
  Walkaway conditions: [list non-negotiables]
  Best alternative: [specific named option, not "I'll find something"]
  Date BATNA reviewed: [YYYY-MM-DD]
```

Adjustments mid-negotiation require a documented reason and a 24-hour delay.

---

## Skill-Negotiation-010: Close With Specificity; Reduce Buyer Remorse

- **Statement**: When agreement is reached, immediately summarize the specific terms in writing and confirm them with the other party. Do not let the deal float on verbal agreement.
- **Context**: End of any successful negotiation. Verbal yes, handshake, "we have a deal" moments.
- **Atomicity**: 88%
- **Evidence**: Voss (Never Split the Difference) on "that's right" close. Confirmation-bias research on commitment-consistency (Cialdini). Verbal-only agreements unwind at 30 to 50 percent in real estate; written confirmations within 24 hours unwind at under 10 percent.
- **Impact**: Locks in agreed terms before either party second-guesses. Surfaces misalignment immediately when memory is fresh.
- **Tags**: negotiation, closing, commitment, written-confirmation

**Pattern**:
1. Recap terms in writing within 1 hour of verbal agreement.
2. Use their language, not yours, for ambiguous terms.
3. End with: "Confirming this matches your understanding."
4. Include date, parties, and any conditions or contingencies.
5. Send via the channel they prefer (email for formal, text for informal).

---

## References

- Fisher and Ury. _Getting to Yes_. Houghton Mifflin, 1981. (BATNA, principled negotiation)
- Voss, Christopher. _Never Split the Difference_. Harper Business, 2016. (Tactical empathy, "that's right" close, calibrated questions)
- Navarro, Joe. _What Every BODY Is Saying_ and _Dangerous Personalities_. (Comfort/discomfort signals, time control)
- Hughes, Chase. _Six-Minute X-Ray_ and PCP framing model. (Perception, Context, Permission)
- Cialdini, Robert. _Influence: The Psychology of Persuasion_. (Commitment-consistency, reciprocity)
- Galinsky, Mussweiler, Chen. Anchoring research. _Journal of Personality and Social Psychology_, multiple papers 2001 to 2009.
- Anthropic Project Deal study (Dec 2025). Internal results on model-tier impact in negotiation tasks.
