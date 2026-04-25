# Negotiation Agent Skills

Category: Deal Intelligence and Offer Analysis

## Skill-Negotiation-001: Always Quantify the Value Gap

- **Statement**: Never describe an offer as "acceptable" or "fair" without first quantifying what value remains uncaptured. State the gap in dollar terms.
- **Context**: Any offer analysis -- real estate, compensation, vendor, resource allocation
- **Atomicity**: 95%
- **Evidence**: Anthropic Project Deal (Dec 2025) -- Opus agents extracted $2-4 more per item than Haiku agents. Participants with weaker agents rated satisfaction identically despite objectively worse outcomes. The gap is invisible without explicit quantification.
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
- Perception: "This isn't [their framing] -- it's [your framing]"
- Context: "Market data / comps / precedent shows [your anchor is normal]"
- Permission: "If you can do X, we can do Y" (give them a path to yes)

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
