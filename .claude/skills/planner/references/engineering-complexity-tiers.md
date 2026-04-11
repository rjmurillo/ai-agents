---
source: wiki/concepts/Engineering Concepts.md
created: 2026-04-11
review-by: 2026-07-11
---

# Engineering Complexity Tiers

Five tiers of engineering difficulty mapped to IC levels and MSec SWE expectations. Use for task classification, design review rigor, and quality gate depth.

## Tier Summary

| Tier | IC Levels | Focus | Complexity |
|------|-----------|-------|------------|
| 1 | IC59-IC60 | Mental models, principles, practices | Simple, component-level |
| 2 | IC61-IC62 | Architecture, patterns, cross-team | Moderate, feature-level |
| 3 | IC63-IC64 | Trade-offs, evolution, operability | Complex, multi-team |
| 4 | IC65-IC67 | Strategy, risk, organizational leadership | Complex, risky, strategic |
| 5 | IC68+ | Legacy thinking, governance, time horizons | Governance and legacy |

## Before Work: Task Classification

| Tier | Design Review Rigor | Reviewer Profile |
|------|-------------------|------------------|
| 1 | Self-review, code review | Any team member |
| 2 | Design doc, peer review | Senior engineer |
| 3 | Design review, cross-team input | Principal or architect |
| 4 | Architecture review, stakeholder alignment | Distinguished or VP-level |
| 5 | Governance board, multi-org consensus | Organization leadership |

## During Work: Patterns and Oversight

| Tier | Appropriate Patterns | Oversight Level |
|------|---------------------|-----------------|
| 1 | SOLID, DRY, basic GoF patterns | Async code review |
| 2 | Resilience patterns, cross-service design | Weekly sync, design doc |
| 3 | CVA, GoF wisdom, strangler fig, error budgets | Active mentorship, milestone gates |
| 4 | OODA loop, pre-mortems, chaos engineering | Steering committee, risk reviews |
| 5 | Lindy effect, second system effect, path dependence | Governance cadence, multi-year planning |

## After Work: Quality Gates

| Tier | Quality Gate | Review Depth |
|------|-------------|--------------|
| 1 | Unit tests pass, code review approved | Single reviewer |
| 2 | Integration tests, design doc updated | Two reviewers, cross-team ack |
| 3 | SLO/SLI defined, operational readiness | Architecture sign-off, load test |
| 4 | Threat model, chaos experiment results | Security review, exec sign-off |
| 5 | Governance approval, deprecation plan | Multi-org review, migration plan |

## IC63 Inflection Point

IC59-IC62 categories focus on execution quality (Business Impact, Design and Delivery, Technical Excellence). IC63+ shifts to leadership categories (Scope of Impact, Leadership, Create Clarity, Generate Energy, Deliver Success, Role Model).

Tier 3 concepts develop the capabilities that differentiate Senior from IC62.

## MSec Categories by Tier

| Tier | MSec Categories |
|------|----------------|
| 1-2 | Business Impact, Execution and Planning, Design and Delivery, Technical Excellence |
| 2 | adds Collaboration and Support |
| 3+ | Scope of Impact, Leadership, Create Clarity, Generate Energy, Deliver Success, Role Model |

## Problem Domain Cross-Reference

| Domain | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Tier 5 |
|--------|--------|--------|--------|--------|--------|
| Decision-Making | Second Order Thinking, Tech Debt Quadrant | Welcome to the Room | Cynefin, Rumsfeld Matrix | OODA Loop, Inversion, Pre-Mortems | - |
| Legacy Systems | Chesterton's Fence, Gall's Law | - | Strangler Fig | - | Lindy Effect, Second System Effect |
| Reliability | Observability Pillars | Resilience Patterns | SLO/SLI/SLA, Error Budgets | Chaos Engineering, Threat Modeling | - |
| Design | Code Qualities, SOLID | Common Patterns, POD | CVA, GoF Wisdom | Design Principles, Services Capabilities | - |

## Planning Usage

When classifying a task during planning:

1. Identify the tier based on scope, risk, and required experience
2. Set design review rigor to match the tier
3. Select patterns appropriate for that tier (avoid over-engineering lower tiers)
4. Define quality gates that match the tier's expectations
5. Assign oversight level proportional to complexity
