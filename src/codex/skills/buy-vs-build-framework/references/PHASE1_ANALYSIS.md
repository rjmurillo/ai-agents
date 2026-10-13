# Phase 1: Deep Analysis - Buy vs Build Framework

**Date**: 2026-02-07
**Tier**: 4 (Principal/VP)
**Timelessness Target**: 9/10

## Input Expansion

### Explicit Requirements

1. Four-phase process: Classify → Analyze → Evaluate → Decide
2. Core vs Context classification (differentiator vs table stakes)
3. TCO Framework with three tiers (quick, standard, deep)
4. Strategic alignment check
5. Decision matrix outputs: Build, Buy, Partner, Defer
6. Integration with: cynefin-classifier, pre-mortem, decision-critic, ADR review
7. Reassessment triggers (decisions aren't permanent)
8. Tiered depth to prevent over-engineering

### Implicit Requirements

1. **Repeatability**: Framework must work for $10K decisions and $10M decisions
2. **Team consensus**: Multiple stakeholders need aligned understanding
3. **Audit trail**: Document rationale for future review/compliance
4. **Time-boxing**: Prevent analysis paralysis
5. **Quantitative + Qualitative**: Both hard numbers and soft factors
6. **Exit criteria**: Know when enough analysis has been done
7. **Risk assessment**: What could go wrong with each option?
8. **Vendor evaluation**: If buying, how to assess vendors
9. **Build capacity assessment**: Can the team actually execute?
10. **Maintenance burden**: Long-term operational costs
11. **Integration complexity**: Fit with existing systems
12. **Competitive dynamics**: Strategic positioning

### Unknown Requirements (Discovered via Regression)

1. **Hybrid strategies**: What if we build AND buy? (e.g., use vendor SDK + custom layer)
2. **Sequential strategies**: Buy now, build later (or vice versa)
3. **Multi-vendor strategy**: Buy from multiple vendors for redundancy
4. **Open source middle ground**: Community-supported vs commercial
5. **Partnership models**: Co-development, revenue share, strategic alliance
6. **Sunset planning**: How to exit/migrate if decision changes
7. **Skill development**: Does build option develop strategic capabilities?
8. **Market signaling**: What does our choice signal to customers/competitors?
9. **Regulatory constraints**: Compliance requirements that force buy vs build
10. **Data sovereignty**: Where data lives, who controls it
11. **Lock-in escape**: Vendor lock-in mitigation strategies
12. **Proof-of-concept stage**: When to do POC before full commitment

## 11 Thinking Models Applied

### 1. First Principles

- **Question**: What problem are we actually solving?
- **Insight**: "Buy vs build" is really "how do we deliver capabilities at optimal cost/speed/quality"
- **Design impact**: Framework must start with capability definition, not solution modes
- **Pattern**: Decouple problem from solution mode

### 2. Inversion

- **Question**: When should we NEVER build? When should we NEVER buy?
- **Never Build**: Commodity capabilities, undifferentiated, no strategic value, team lacks skills, time-critical
- **Never Buy**: Core IP, competitive secret sauce, requires 100% control, no viable vendors, regulatory restrictions
- **Design impact**: Create explicit "red line" criteria that skip analysis

### 3. Second-Order Effects

- **Question**: What happens after the decision?
- **Build**: Team gains skills, maintenance burden increases, opportunity cost on other projects
- **Buy**: Vendor dependency, platform constraints, integration debt
- **Partner**: Shared roadmap control, revenue complexity, relationship overhead
- **Design impact**: Include "year 2, year 5" consequence analysis

### 4. Systems Thinking

- **Question**: How does this decision affect the broader system?
- **Insight**: Buy vs build impacts hiring, team structure, vendor relationships, budget cycles
- **Design impact**: Include "ecosystem impact" assessment (team, org, market)

### 5. Probabilistic Thinking

- **Question**: What's the distribution of outcomes?
- **Insight**: Not binary success/failure, but spectrum of ROI outcomes
- **Design impact**: TCO should include confidence intervals, not point estimates

### 6. Regret Minimization

- **Question**: Which decision will we regret least in 3 years?
- **Insight**: Regret often comes from missed opportunities, not failed projects
- **Design impact**: Include "opportunity cost" and "strategic optionality" in decision matrix

### 7. Compounding Effects

- **Question**: What decision creates future leverage?
- **Build**: Team capability compounds, platform grows, IP accumulates
- **Buy**: Time savings compound, vendor innovations flow in, integration debt grows
- **Design impact**: Separate "initial cost" from "compounding value"

### 8. Optionality

- **Question**: Which decision preserves future options?
- **Insight**: "Defer" is a valid decision; reversible choices are better than irreversible
- **Design impact**: Rate decisions on reversibility; prefer options that keep doors open

### 9. Skin in the Game

- **Question**: Who bears the consequences?
- **Insight**: Decision-makers must be accountable for outcomes
- **Design impact**: Track decision-maker identity in ADR; measure outcomes

### 10. Asymmetric Upside

- **Question**: Which option has unlimited upside?
- **Build**: Can become platform, productized, spun out
- **Buy**: Limited upside (you get what vendor offers)
- **Partner**: Shared upside (revenue split, market expansion)
- **Design impact**: Include "asymmetric upside potential" scoring

### 11. Time Horizon

- **Question**: When do we need this capability?
- **Short-term (<6mo)**: Buy strongly favored (time value of money)
- **Medium-term (6-24mo)**: Nuanced; depends on strategic value
- **Long-term (2y+)**: Build may be favored if core capability
- **Design impact**: Time horizon is first-order input to framework

## Automation Lens

### Opportunities for Scripts

1. **TCO Calculator** (`scripts/calculate_tco.py`)
   - Input: Cost assumptions, time horizons, growth rates
   - Output: NPV, IRR, break-even timeline
   - Exit codes: 0=success, 10=negative NPV warning

2. **Decision Matrix Scorer** (`scripts/score_decision.py`)
   - Input: Criteria weights, option scores
   - Output: Weighted scores, sensitivity analysis
   - Exit codes: 0=clear winner, 1=tie requires human judgment

3. **Reassessment Trigger** (`scripts/check_reassessment_triggers.py`)
   - Input: Original assumptions, current state
   - Output: Drift analysis, re-evaluation recommendation
   - Exit codes: 0=assumptions hold, 11=reassessment required

4. **Vendor Scorecard** (`scripts/score_vendor.py`)
   - Input: Vendor data (stability, pricing, features)
   - Output: Vendor risk score
   - Exit codes: 0=pass, 10=yellow flag, 11=red flag

### Self-Verification Patterns

- TCO script validates that all cost categories are addressed
- Decision matrix validates that criteria are MECE (mutually exclusive, collectively exhaustive)
- Reassessment trigger validates original assumptions are still documented

## Tiered Depth Analysis

### Tier 1: Quick (1-2 hours)

- **When**: <$50K decision, low strategic impact, reversible
- **Process**: Core vs Context + simple TCO + gut check
- **Output**: Go/No-go decision

### Tier 2: Standard (1-2 days)

- **When**: $50K-$500K, moderate strategic impact, semi-reversible
- **Process**: Full four phases, basic TCO, stakeholder review
- **Output**: Detailed decision matrix + ADR

### Tier 3: Deep (1-2 weeks)

- **When**: >$500K, high strategic impact, irreversible
- **Process**: Full four phases + POCs + external research + consensus panel
- **Output**: Comprehensive ADR + TCO model + risk analysis

## Integration Points

### 1. cynefin-classifier

- **When**: Before starting buy-vs-build (Phase 0)
- **Why**: Determines if problem is complicated (analyze) vs complex (experiment)
- **Integration**: If problem is Complex → favor Buy/Partner (reduce risk)

### 2. pre-mortem

- **When**: After initial decision, before commitment
- **Why**: Surface hidden failure modes
- **Integration**: Run pre-mortem on chosen option; if >5 severe risks surface → reconsider

### 3. decision-critic

- **When**: After decision matrix complete, before ADR
- **Why**: Challenge assumptions and verify claims
- **Integration**: Feed decision rationale to critic; incorporate feedback

### 4. ADR review

- **When**: After decision finalized
- **Why**: Multi-agent consensus on strategic decisions
- **Integration**: buy-vs-build decisions automatically trigger ADR creation + review

## Reassessment Triggers

Decisions should be re-evaluated when:

1. **Cost assumption changes >20%**: Vendor pricing changes, build estimates revised
2. **Time horizon shifts**: Originally 3-year need, now 6-month need
3. **Strategic priority shifts**: Capability moves from context to core (or vice versa)
4. **Vendor viability concerns**: M&A, financial troubles, product EOL
5. **Team capacity changes**: Key engineers leave, hiring surge enables build option
6. **Competitive dynamics shift**: Competitor launches similar feature (urgency increases)
7. **Regulatory changes**: New compliance requirements favor/disfavor certain options
8. **Technology disruption**: New technology makes previous decision obsolete
9. **Customer demand signal**: Customers explicitly request self-hosted vs SaaS
10. **Annual review**: Scheduled check-in (every 12 months minimum)

## Timelessness Analysis

### Why this framework is timeless (9/10)

1. **Economic fundamentals unchanged**: Make vs buy tradeoff existed in 1920s, will exist in 2050s
2. **Strategic concepts durable**: Core vs context from Wardley Mapping (2005), still relevant 20+ years later
3. **Decision structures universal**: Four-phase process works for software, hardware, services
4. **Human psychology constant**: Cognitive biases (sunk cost, confirmation bias) don't change
5. **Organization patterns stable**: Principal/VP decision-making authority stable across decades

### What could change (-1 point)

1. **AI automation**: AI code generation could shift build costs radically downward
2. **Vendor consolidation**: If only 1-2 vendors exist, "buy" calculus changes
3. **Open source maturity**: More mature OSS could create "free" middle ground

**Mitigation**: Framework explicitly includes "Defer" option and reassessment triggers to adapt to these shifts.

## Conclusion

Framework is READY for Phase 2 specification generation.

**Key decisions:**

- Tiered depth (3 tiers based on decision magnitude)
- Four-phase process with explicit exit criteria at each phase
- Integration with 4 existing skills (cynefin, pre-mortem, decision-critic, ADR)
- 4 Python scripts for autonomous operation
- 10 reassessment triggers for decision maintenance
- Timelessness score: 9/10 (economic fundamentals + strategic concepts)

**Next**: Generate XML specification (Phase 2)
