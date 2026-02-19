# Buy vs Build Framework Skill

**Created**: 2026-02-07
**Location**: `.claude/skills/buy-vs-build-framework/`
**Status**: Production-ready
**Tier**: 4 (Principal/VP level)
**Timelessness**: 9/10

## Overview

Strategic framework for evaluating build, buy, partner, or defer decisions with four-phase process, tiered TCO analysis, and integration with decision quality tools.

## When to Use

- Evaluating whether to develop in-house vs purchase vendor solution
- Strategic capability investment requires multi-stakeholder alignment
- Need structured TCO analysis to justify budget allocation
- Decision has long-term strategic implications (2+ year horizon)
- Team split on approach and need objective framework

## Process Phases

### Phase 0: Depth Selection
- **Quick** (<$50K, 1-2 hours): Core vs Context + Simple TCO + Go/No-go
- **Standard** ($50K-$500K, 1-2 days): Full 4 phases + Decision matrix + ADR
- **Deep** (>$500K, 1-2 weeks): Full 4 phases + POCs + External research + Consensus + Comprehensive ADR

### Phase 1: Classify (Core vs Context)
- Determine if capability is competitive differentiator (Core) or table stakes (Context)
- Strategic importance scoring (1-10)
- Red line criteria (Never Build / Never Buy)
- Optional integration with cynefin-classifier

### Phase 2: Analyze (TCO + Capacity)
- Calculate NPV, IRR, break-even for Build/Buy/Partner options
- Cost categories: Initial, Ongoing, Hidden
- Team capacity assessment (skills, bandwidth, maintenance)
- Sensitivity analysis on key assumptions

### Phase 3: Evaluate (Decision Matrix)
- Score across Strategic (40%), Operational (30%), Risk (30%) dimensions
- Pre-mortem on leading option (required)
- Sensitivity analysis on criteria weights

### Phase 4: Decide (Final Decision + ADR)
- Decision outputs: Build, Buy, Partner, Defer
- Integration with decision-critic for validation
- Automatic ADR creation + adr-review for Standard/Deep tier
- Reassessment plan with 10 triggers

## Scripts

All scripts in `scripts/` directory:

### 1. calculate_tco.py
- Calculate NPV, IRR, break-even timeline
- Exit codes: 0=success, 10=negative NPV warning, 11=validation failure

### 2. score_decision.py
- Weighted decision scoring with sensitivity analysis
- Exit codes: 0=clear winner (>20% gap), 1=tie (<10% gap)

### 3. check_reassessment_triggers.py
- Detect assumption drift, recommend re-evaluation
- Exit codes: 0=assumptions hold, 10=minor drift, 11=major drift (>20%)

### 4. score_vendor.py
- Score vendor stability, pricing, features, support
- Exit codes: 0=pass (>70), 10=yellow flag (50-70), 11=red flag (<50)

## Reassessment Triggers

Decisions should be re-evaluated when:

1. Cost assumption changes >20%
2. Time horizon shifts materially
3. Strategic priority shifts (context ↔ core)
4. Vendor viability concerns (M&A, financials, EOL)
5. Team capacity changes (key departures, hiring surge)
6. Competitive dynamics shift (urgency increases)
7. Regulatory changes
8. Technology disruption
9. Customer demand signal
10. Annual review (minimum every 12 months)

## Integration Points

| Skill | Phase | Purpose |
|-------|-------|---------|
| cynefin-classifier | Pre-Phase 1 | Determine if problem is analyzable (Complicated) vs requires experimentation (Complex) |
| pre-mortem | Phase 3 | Surface hidden failure modes in leading option |
| decision-critic | Phase 4 | Validate assumptions, challenge claims |
| adr-review | Phase 4 | Multi-agent consensus on strategic decisions |

## Timelessness Rationale

**Score: 9/10**

**Why timeless:**
- Economic fundamentals of make-vs-buy tradeoff unchanged for 100+ years
- Strategic concepts (core vs context) from Wardley Mapping remain relevant 20+ years later
- Decision structures universal across domains
- Human cognitive biases don't change
- Principal/VP decision-making authority stable across decades

**What could change (-1 point):**
- AI code generation could shift build costs radically downward
- Vendor consolidation changes buy calculus
- Open source maturity creates "free" middle ground

**Mitigation**: Framework includes "Defer" option and reassessment triggers to adapt.

## Related Skills

- [cynefin-classifier](../../.claude/skills/cynefin-classifier/SKILL.md): Problem domain classification
- [pre-mortem](../../.claude/skills/pre-mortem/SKILL.md): Risk identification
- [decision-critic](../../.claude/skills/decision-critic/SKILL.md): Decision validation
- [adr-review](../../.claude/skills/adr-review/SKILL.md): Multi-agent consensus
- [planner](../../.claude/skills/planner/SKILL.md): Post-decision execution planning

## Anti-Patterns

- Using framework for trivial decisions (<$10K, reversible)
- Skipping pre-mortem on high-risk decisions
- Not documenting rationale (no ADR)
- Forgetting reassessment plan
- Optimizing for single dimension (cost only)

## Skill Metadata

```yaml
name: buy-vs-build-framework
version: 1.0.0
model: claude-opus-4-5
tier: 4
timelessness: 9
license: MIT
```

## Usage Example

```
User: "evaluate build vs buy for authentication system"

Agent: [Activates buy-vs-build-framework]
1. Phase 0: Select depth (Standard tier, $200K budget)
2. Phase 1: Classify (Context capability, score 4/10)
3. Phase 2: TCO analysis ($50K initial + $20K/yr buy vs $200K initial + $30K/yr build)
4. Phase 3: Decision matrix (Buy scores 7.5, Build scores 6.2)
5. Phase 4: Recommend BUY, create ADR, set 6-month review
```
