---
source: wiki/concepts/Engineering Concepts.md
created: 2026-04-11
review-by: 2026-07-11
---

# Engineering Complexity Tiers

Five tiers of engineering difficulty mapped to experience levels and focus areas. Use for task classification, design review rigor, and quality gate depth.

## Tier Summary

| Tier | Level | Focus | Autonomy |
|------|-------|-------|----------|
| 1 | Entry (<2 years) | Pre-defined, scoped punch list items. Clear inputs and outputs. | Low. Tasks are assigned with explicit acceptance criteria. |
| 2 | Junior (2-5 years) | More autonomy, broader scope. Owns features within a defined boundary. | Moderate. Can make implementation decisions within constraints. |
| 3 | Senior (5-10 years) | Complex, multi-component problems. Trade-offs, operability, evolution. | High. Defines approach, identifies risks, mentors others. |
| 4 | Staff (10-15 years) | Complex, risky, strategic problems. Brings clarity to ambiguous situations. | Very high. Sets technical direction for a product or domain. |
| 5 | Principal (15+ years) | Governance, legacy, organizational clarity. Brings clarity to groups, not just products. | Full. Shapes engineering culture and multi-year technical strategy. |

## The Inflection Point: Senior to Staff

Senior to Staff is where execution stops being the primary measure of value. A Senior's output is code. A Staff's output is decisions, clarity, and team unblocking.

Staff engineers work in the white space between teams (Larson). Senior engineers solve problems handed to them. Staff engineers identify which problems matter.

## Before Work: Task Classification

| Tier | Design Review Rigor | Reviewer Profile |
|------|-------------------|------------------|
| 1 | Self-review, code review | Any team member |
| 2 | Design doc, peer review | Senior engineer |
| 3 | Design review, cross-team input | Staff or architect |
| 4 | Architecture review, stakeholder alignment | Principal or director |
| 5 | Governance board, multi-org consensus | Organization leadership |

## During Work: Patterns and Oversight

| Tier | Appropriate Patterns | Oversight Level |
|------|---------------------|-----------------|
| 1 | SOLID, DRY, basic GoF patterns | Async code review, pairing |
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

## The Senior Inflection Point

Entry and Junior tiers focus on execution quality: delivering working code, following standards, and building technical depth. Senior and above shift to leadership: scope of impact, creating clarity for others, and making the right trade-offs under ambiguity.

Tier 3 is where engineers stop being measured on what they build and start being measured on what they enable others to build.

## Staff vs Principal in Practice

| Dimension | Staff | Principal |
|-----------|-------|-----------|
| Scope | One org, one domain | Multiple orgs, whole company |
| Ambiguity target | Clarifies a team's direction | Clarifies direction across groups |
| Influence | Peer teams | Org-wide or company-wide |
| Code contribution | Significant | Strategic |

## Problem Domain Cross-Reference

| Domain | Tier 1 (Entry) | Tier 2 (Junior) | Tier 3 (Senior) | Tier 4 (Staff) | Tier 5 (Principal) |
|--------|----------------|-----------------|-----------------|----------------|-------------------|
| Decision-Making | Second Order Thinking | Tech Debt Quadrant | Cynefin, Rumsfeld Matrix | OODA Loop, Inversion, Pre-Mortems | Wardley Mapping |
| Legacy Systems | Chesterton's Fence, Gall's Law | Boy Scout Rule | Strangler Fig | Migration Planning | Lindy Effect, Second System Effect |
| Reliability | Observability Pillars | Resilience Patterns | SLO/SLI/SLA, Error Budgets | Chaos Engineering, Threat Modeling | Platform Strategy |
| Design | Code Qualities, SOLID | Common Patterns, POD | CVA, GoF Wisdom | Design Principles, Services | Governance Frameworks |

## Analysis Usage

When analyzing code or architecture:

1. Classify the component's complexity tier based on scope and dependencies
2. Evaluate whether patterns match the appropriate tier (over-engineering or under-engineering)
3. Check quality gates against tier expectations
4. Flag mismatches between component tier and actual review/oversight applied
5. Recommend tier-appropriate improvements in findings
