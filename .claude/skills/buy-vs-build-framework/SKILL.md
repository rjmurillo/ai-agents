---
name: buy-vs-build-framework
version: 1.0.0
model: claude-opus-4-5
description: Strategic framework for evaluating build buy partner or defer decisions with four-phase process tiered TCO analysis and integration with decision quality tools
license: MIT
metadata:
  tier: 4
  timelessness: 9
  author: SkillForge
---

# Buy vs Build Framework

When this skill activates, you become a strategic sourcing advisor for Principal+ leaders. Your role is to guide systematic evaluation of build, buy, partner, or defer decisions through a four-phase framework that prevents both under-analysis (gut decisions) and over-analysis (paralysis).

## Triggers

Activate when the user:

- `evaluate build vs buy for {capability}`
- `should we build or buy {system}`
- `core vs context analysis`
- `strategic sourcing decision for {feature}`
- `make or buy decision`

## When to Use

Use this skill when:

- Evaluating whether to develop in-house vs purchase vendor solution
- Strategic capability investment requires multi-stakeholder alignment
- Need structured TCO analysis to justify budget allocation
- Decision has long-term strategic implications (2+ year horizon)
- Team split on approach and need objective framework

Use [cynefin-classifier](../cynefin-classifier/SKILL.md) first if:

- Unsure whether problem is analyzable (Complicated) or requires experimentation (Complex)

Use [decision-critic](../decision-critic/SKILL.md) instead if:

- Decision already made and you need validation/challenge

Use [planner](../planner/SKILL.md) instead if:

- Sourcing decision already made, need execution plan

## Quick Reference

| Phase | Duration | Output |
|-------|----------|--------|
| 0. Depth Selection | 5 min | Quick / Standard / Deep tier |
| 1. Classify | 30 min - 2 hours | Core vs Context + Strategic score |
| 2. Analyze | 1 hour - 1 day | TCO + Team capacity assessment |
| 3. Evaluate | 2 hours - 3 days | Decision matrix + Pre-mortem |
| 4. Decide | 1 hour - 1 week | Final decision + ADR + Reassessment plan |

## Process

### Phase 0: Depth Selection

Select appropriate analysis depth to prevent over-engineering.

#### Decision Matrix:

| Tier | Budget | Impact | Reversibility | Duration | Output |
|------|--------|--------|---------------|----------|--------|
| **Quick** | <$50K | Low | Easy | 1-2 hours | Core vs Context + Simple TCO + Go/No-go |
| **Standard** | $50K-$500K | Medium | Moderate | 1-2 days | Full 4 phases + Decision matrix + ADR |
| **Deep** | >$500K | High | Hard | 1-2 weeks | Full 4 phases + POCs + External research + Consensus + Comprehensive ADR |

**Why:** Time-box effort proportional to decision magnitude. Prevents analysis paralysis on small decisions while ensuring rigor for strategic decisions.

#### Script:

```text
python3 scripts/select_depth.py --budget 100000 --impact medium --reversibility moderate
# Output: STANDARD tier (1-2 days, full 4 phases)
```text

### Phase 1: Classify (Core vs Context)

**Purpose:** Determine if capability is Core (competitive differentiator) or Context (table stakes).

#### Framework:

```text
CORE                                    CONTEXT
Competitive differentiator              Table stakes
Unique to business model                Industry-standard
Source of customer value                Required but not differentiating

Customers choose you BECAUSE of this    Customers assume you have this
Amazon's recommendation engine          Auth systems
Netflix's content algorithm             Payment processing
Uber's matching system                  Email delivery

Default: BUILD                          Default: BUY
(unless constraints prevent)            (unless no viable vendors)
```text

#### Integration Points:

1. **Optional pre-step:** Run [cynefin-classifier](../cynefin-classifier/SKILL.md) if problem domain unclear
   - Complex → favor Buy/Partner (reduce risk through experimentation)
   - Complicated → proceed with analysis

#### Outputs:

1. Core or Context classification with 3+ supporting reasons
2. Strategic importance score (1-10)
3. Red line criteria:
   - **Never Build:** Commodity, undifferentiated, no strategic value, team lacks skills, time-critical
   - **Never Buy:** Core IP, competitive secret sauce, 100% control required, no viable vendors, regulatory restrictions

#### Exit Criteria:

- [ ] Classification documented with justification
- [ ] Stakeholder consensus (or disagreement documented)
- [ ] Strategic importance score assigned

**See:** [references/core-vs-context.md](references/core-vs-context.md) for detailed framework

### Phase 2: Analyze (TCO + Capacity)

**Purpose:** Quantify total cost of ownership and assess team capacity.

#### TCO Script:

```text
python3 scripts/calculate_tco.py \
  --build-initial 500000 \
  --build-ongoing 100000 \
  --buy-initial 50000 \
  --buy-ongoing 200000 \
  --partner-initial 100000 \
  --partner-ongoing 150000 \
  --discount-rate 0.12 \
  --years 5

# Output:
# NPV (Build): $1.2M
# NPV (Buy): $1.5M
# NPV (Partner): $1.3M
# Break-even: Year 3.2
# Sensitivity: Discount rate (±20% → ±$300K)
```text

#### Cost Categories:

| Category | Build | Buy | Partner |
|----------|-------|-----|---------|
| **Initial** | Engineering time, design, architecture, tooling | License fees, implementation services, integration, training | Integration work, legal agreements, POC |
| **Ongoing** | Maintenance, bug fixes, features, infrastructure, support | Subscription fees, support contracts, upgrades | Revenue share, relationship management, co-dev coordination |
| **Hidden** | Opportunity cost, onboarding, tech debt | Vendor lock-in, integration debt, workflow constraints | Roadmap misalignment, partner dependency, revenue complexity |

#### Capacity Assessment:

Answer these questions:

1. Does team have required skills? (If no, add training/hiring costs)
2. Does team have capacity without delaying strategic projects?
3. Can team maintain long-term? (Avoid orphaned code)
4. Does build option develop strategic capabilities for future?

#### Exit Criteria:

- [ ] TCO calculated for 3, 5, 10 year horizons
- [ ] Sensitivity analysis identifies top 3 cost drivers
- [ ] Team capacity assessment documented

**See:** [references/tco-methodology.md](references/tco-methodology.md) for calculation details

### Phase 3: Evaluate (Decision Matrix)

**Purpose:** Score options across strategic, operational, and risk dimensions.

#### Decision Criteria:

```text
python3 scripts/score_decision.py \
  --criteria-file decision-criteria.json \
  --options build,buy,partner

# Output:
# Build: 7.8 (Strategic: 9.0, Operational: 6.5, Risk: 8.0)
# Buy: 6.2 (Strategic: 4.0, Operational: 8.5, Risk: 6.0)
# Partner: 7.1 (Strategic: 7.5, Operational: 6.0, Risk: 7.5)
# Winner: BUILD (confidence: MEDIUM, 9% gap)
```text

#### Criteria Weights:

| Dimension | Weight | Criteria |
|-----------|--------|----------|
| **Strategic** | 40% | Alignment, Market signaling, Optionality, Asymmetric upside |
| **Operational** | 30% | Time to value, Team fit, Integration complexity, Maintenance burden |
| **Risk** | 30% | Vendor risk, Execution risk, Regulatory risk, Lock-in risk |

#### Integration Points:

1. **Required:** Run [pre-mortem](../pre-mortem/SKILL.md) on leading option
   - If >5 severe risks surface → reconsider decision
   - Document mitigations for top 3 risks

#### Exit Criteria:

- [ ] All criteria scored for all options (with justifications)
- [ ] Pre-mortem completed for leading option
- [ ] If tie (<10% gap), document tie-breaker rationale

**See:** [templates/decision-matrix.md](templates/decision-matrix.md) for scoring worksheet

### Phase 4: Decide (Final Decision + ADR)

**Purpose:** Make final decision, document rationale, plan reassessment.

#### Decision Matrix:

| Option | When to Choose |
|--------|----------------|
| **Build** | Core capability + team capacity + favorable TCO<br>No viable vendors OR vendor lock-in unacceptable<br>Strategic capability development desired |
| **Buy** | Context capability + viable vendors + faster time to value<br>Team lacks capacity OR skills<br>Commodity capability with mature market |
| **Partner** | Shared value creation (rev share, co-development)<br>Strategic alliance benefits beyond technology<br>Neither build nor buy individually compelling |
| **Defer** | Unclear requirements OR high uncertainty<br>Market immature (wait for consolidation)<br>Problem may not need solving (validate demand first) |

#### Integration Points:

1. **Required:** Feed final rationale to [decision-critic](../decision-critic/SKILL.md)
   - Validate assumptions, challenge claims
   - Address any blocking concerns

2. **Automatic (Standard/Deep tier):** Trigger [adr-review](../adr-review/SKILL.md)
   - Multi-agent consensus on strategic decisions
   - Create ADR with template below

#### ADR Template:

```python
# ADR-NNN: [Build/Buy/Partner/Defer] {Capability Name}

## Decision

We will [BUILD/BUY/PARTNER/DEFER] {capability}.

## Context

{Problem being solved, strategic importance, business drivers}

## Considered Options

1. **Build**: {Summary, pros/cons, TCO}
2. **Buy**: {Summary, pros/cons, TCO, vendor options}
3. **Partner**: {Summary, pros/cons, TCO, partnership models}
4. **Defer**: {Summary, validation approach}

## Decision Drivers

1. {Top factor that determined outcome}
2. {Second most important factor}
3. {Third most important factor}

## Consequences

#### Expected Outcomes:
- {Positive outcome 1}
- {Positive outcome 2}

#### Risks:
- {Risk 1 + Mitigation}
- {Risk 2 + Mitigation}

## Reassessment Triggers

- Cost assumption changes >20%
- Time horizon shifts materially
- Strategic priority shifts (context to core or vice versa)
- Vendor viability concerns (M&A, financials, EOL)
- Team capacity changes (key departures, hiring surge)
- Competitive dynamics shift (urgency increases)
- Regulatory changes
- Technology disruption
- Customer demand signal
- **Annual review:** {Date}

## Decision-Maker

{Name, Title} on {Date}
```text

#### Reassessment Plan:

```python
# Run quarterly to detect assumption drift
python3 scripts/check_reassessment_triggers.py \
  --adr-file architecture/ADR-123-build-payments.md \
  --current-state current-state.json

# Output:
# Status: REASSESSMENT_REQUIRED
# Drift: Vendor pricing changed 25% (trigger: >20%)
# Recommendation: Run Phase 2 (TCO) analysis with updated costs
```text

#### Exit Criteria:

- [ ] Decision documented in ADR (Standard/Deep tier)
- [ ] Decision-critic validation passed (no blocking issues)
- [ ] Reassessment schedule established (6, 12, 24 months)
- [ ] Stakeholder sign-off obtained

## Scripts

### calculate_tco.py

Calculate NPV, IRR, break-even timeline for build/buy/partner options.

```text
python3 scripts/calculate_tco.py --help

# Required flags:
#   --build-initial FLOAT       Initial build costs
#   --build-ongoing FLOAT       Annual build costs
#   --buy-initial FLOAT         Initial buy costs
#   --buy-ongoing FLOAT         Annual buy costs
#   --partner-initial FLOAT     Initial partner costs
#   --partner-ongoing FLOAT     Annual partner costs
#   --discount-rate FLOAT       Discount rate (0.10 = 10%)
#   --years INT                 Analysis horizon (3, 5, or 10)

# Exit codes:
#   0: Success
#   10: Warning (negative NPV detected)
#   11: Error (missing cost categories)
```text

### score_decision.py

Calculate weighted decision scores with sensitivity analysis.

```text
python3 scripts/score_decision.py --help

# Required flags:
#   --criteria-file PATH        JSON file with criteria weights and scores

# Exit codes:
#   0: Clear winner (>20% score gap)
#   1: Tie requires human judgment (scores within 10%)
```text

### check_reassessment_triggers.py

Detect assumption drift, recommend re-evaluation.

```text
python3 scripts/check_reassessment_triggers.py --help

# Required flags:
#   --adr-file PATH             ADR markdown file
#   --current-state PATH        JSON with current assumptions

# Exit codes:
#   0: Assumptions hold, stay course
#   10: Minor drift (<20%), monitor closely
#   11: Major drift (>20%), re-evaluation required
```text

### score_vendor.py

Score vendor stability, pricing, feature fit.

```text
python3 scripts/score_vendor.py --help

# Required flags:
#   --vendor-data PATH          JSON file with vendor information

# Exit codes:
#   0: Pass (score >70)
#   10: Yellow flag (score 50-70)
#   11: Red flag (score <50)
```text

## Templates

All templates available in `templates/` directory:

- `core-vs-context-analysis.md` - Phase 1 classification worksheet
- `tco-analysis.md` - Phase 2 TCO calculation worksheet
- `decision-matrix.md` - Phase 3 multi-criteria scoring
- `adr-buy-vs-build.md` - Phase 4 ADR template

## References

Deep-dive documentation in `references/` directory:

- `core-vs-context.md` - Core vs Context framework from Wardley Mapping
- `tco-methodology.md` - TCO calculation best practices
- `partnership-models.md` - Partnership structures (co-dev, revenue share, alliance)
- `vendor-evaluation.md` - Vendor assessment framework
- `reassessment-playbook.md` - How to re-evaluate when assumptions change

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Using framework for trivial decisions (<$10K, reversible) | Analysis paralysis | Use judgment, skip framework |
| Skipping pre-mortem on high-risk decisions | Misses hidden failure modes | Always run pre-mortem in Phase 3 |
| Not documenting rationale | Future team can't understand why | Create ADR (Standard/Deep tier) |
| Forgetting reassessment plan | Decision becomes stale | Set calendar reminders for reviews |
| Optimizing for single dimension (only cost) | Ignores strategic value | Use full decision matrix |

## Related Skills

| Skill | Relationship |
|-------|--------------|
| [cynefin-classifier](../cynefin-classifier/SKILL.md) | Pre-step to determine problem domain |
| [pre-mortem](../pre-mortem/SKILL.md) | Phase 3 risk identification |
| [decision-critic](../decision-critic/SKILL.md) | Phase 4 validation |
| [adr-review](../adr-review/SKILL.md) | Phase 4 multi-agent consensus |
| [planner](../planner/SKILL.md) | Post-decision execution planning |

## Timelessness

#### Score: 9/10

#### Why timeless:

- Economic fundamentals of make-vs-buy unchanged for 100+ years (industrial revolution → present)
- Strategic concepts (core vs context) from Wardley Mapping remain relevant 20+ years later
- Decision structures universal across software, hardware, services
- Human cognitive biases (sunk cost, confirmation bias) don't change
- Principal/VP decision-making authority stable across decades

#### What could change (-1 point):

- AI code generation could shift build costs radically downward
- Vendor consolidation (only 1-2 vendors) changes buy calculus
- Open source maturity creates "free" middle ground

**Mitigation:** Framework includes "Defer" option and reassessment triggers to adapt to these shifts.
