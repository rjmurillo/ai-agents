---
name: negotiation
version: 1.0.0
model: claude-opus-4-6
description: Deal intelligence skill for offer analysis and counter-proposal drafting. Trigger on `review this offer`, `analyze counter`, `value gap`, `draft counter`, `should I walk`. Apply when reviewing any offer (real estate, compensation, vendor, resource allocation) or designing negotiation analysis behavior in agentic systems. Quantifies value gaps, applies RADAR protocol, enforces senior-tier model routing.
license: MIT
metadata:
  domains: [negotiation, deal-intelligence, behavioral-influence, agent-design]
  type: knowledge
  source: Anthropic Project Deal (Dec 2025), Fisher and Ury, Voss, Navarro, Hughes, Cialdini, Galinsky
---

# Negotiation Skill

Codifies deal intelligence behavior. Use when reviewing any offer or
designing how an agentic system should analyze and counter-propose.
The full crystallized skill set lives in `references/skills.md`.

## Triggers

| Phrase | Context |
|--------|---------|
| `review this offer` | Real estate, compensation, vendor, resource allocation |
| `what's the value gap` | Quantification request |
| `draft a counter` | Counter-proposal drafting |
| `should I walk` | Walkaway analysis |
| `anchor first or wait` | Information-asymmetry decision |

Skip when:

- The change is descriptive ("explain how anchoring works") rather than
  applied. Use a knowledge response, not the skill.
- The artifact is not an offer or counter (e.g., a status update).

## Process

Apply the RADAR protocol in order. Skipping a step is the most common
failure mode and the rule against it is load-bearing.

### Phase 1: Read

Extract every term in the offer. List anchors, hedging, urgency
signals, omissions. Do not interpret yet.

### Phase 2: Analyze

Map ZOPA, BATNA, information asymmetry, value gap. Quantify the gap
in dollars before any qualitative language. See
`references/skills.md` Skill-Negotiation-001.

### Phase 3: Design

Draft PCP framing (Perception, Context, Permission) before producing
a number. Whoever defines the frame controls the negotiation. See
Skill-Negotiation-003.

### Phase 4: Assess

Run the invisible-disadvantage check. Compare risk of countering vs.
accepting. Apply the anchor-first decision rule
(Skill-Negotiation-008) and BATNA discipline
(Skill-Negotiation-009).

### Phase 5: Review

Produce a DRAFT counter with explicit human approval gate. Specific
closing pattern from Skill-Negotiation-010 applies once verbal
agreement is reached.

## Verification

Output is acceptable when ALL of the following hold:

- [ ] Offer net value, achievable value, and gap are quantified in
      dollars (Skill-Negotiation-001 implementation block).
- [ ] At least one written-signal observation from
      Skill-Negotiation-007 is cited if the offer arrived in writing.
- [ ] Counter-proposal carries PCP framing in the output, not just a
      number (Skill-Negotiation-003).
- [ ] BATNA worksheet (Skill-Negotiation-009) is filled before the
      first counter goes out.
- [ ] Bundling rule (Skill-Negotiation-005) is honored: no
      single-dimension concession appears in the counter.
- [ ] Final output is marked DRAFT and waits for explicit human
      approval before sending.
- [ ] If routed through an agentic system, the negotiation analysis
      runs on a senior-tier model (Skill-Negotiation-006).

## Anti-Patterns

- **Reactive countering**: producing a number before completing
  Phase 1 (Read) and Phase 2 (Analyze). Frame is then defined by the
  other party.
- **Single-dimension concessions**: trading price without extracting
  value on another dimension. Drains leverage item by item.
- **Matching urgency**: accepting tactical deadlines as if they were
  genuine. Slow down and require external justification.
- **Mid-negotiation BATNA drift**: relaxing the walkaway under
  sunk-cost pressure. Pre-commit in writing; require 24h delay for
  any adjustment.
- **Routing to a junior model**: model capability gap is the only
  variable that consistently changes negotiation outcomes (Project
  Deal). Prompt style does not compensate. See
  Skill-Negotiation-006.
- **Verbal-only close**: leaves the deal exposed to remorse and
  selective memory. Always confirm in writing within 1 hour
  (Skill-Negotiation-010).

## Extension Points

- **New domain (insurance, M&A, etc.)**: add a domain-specific
  reference under `references/` mapping the domain's leverage points
  onto the 10 skills. Do not edit the canonical skill list.
- **Behavioral framework swaps**: the PCP framing,
  comfort/discomfort signal table, and BATNA worksheet are pluggable.
  Replace via a sibling reference if a different model fits the
  domain better.
- **Agent integration**: when wiring the skill into an agentic
  system, include `model_tier: opus` (or equivalent senior tier) in
  the agent template. See `templates/agents/negotiation.shared.md`.

## References

- `references/skills.md` — full canonical 10 crystallized skills
  with implementation patterns, evidence citations, and tags.
- Source citations: Fisher and Ury _Getting to Yes_, Voss _Never Split
  the Difference_, Navarro _What Every BODY Is Saying_, Hughes
  _Six-Minute X-Ray_, Cialdini _Influence_, Galinsky/Mussweiler/Chen
  anchoring research, Anthropic Project Deal (Dec 2025; internal
  research, data not publicly available for audit; specific dollar
  values illustrative).
