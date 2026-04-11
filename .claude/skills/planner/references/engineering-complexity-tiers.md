---
source: wiki/concepts/Engineering Concepts.md
created: 2026-04-11
review-by: 2026-07-11
---

# Engineering Complexity Tiers

Five tiers of engineering difficulty mapped to experience levels and focus areas. Use for milestone design, task decomposition, and review gate calibration.

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

## Planning Implications

| Tier | Milestone Design | Decomposition Style |
|------|-----------------|---------------------|
| 1 | Batch into larger milestones. Each task has explicit done criteria. | Punch list. Each item is self-contained with clear inputs/outputs. |
| 2 | Feature-level milestones. Design doc required. | Feature breakdown. Owner decides implementation within boundaries. |
| 3 | Independent milestones with design review gates. | Risk-based decomposition. Owner identifies approach and risks. |
| 4 | Proof-of-concept milestone first. ADR required. Stakeholder alignment. | Strategic decomposition with explicit rollback plans per milestone. |
| 5 | Governance milestone with multi-org consensus. Multi-year horizon. | Evolutionary decomposition. Each increment must deliver standalone value. |

## Review Gate Calibration

| Tier | Before Work | During Work | After Work |
|------|-------------|-------------|------------|
| 1 | Self-review, code review | Async review | Unit tests, single reviewer |
| 2 | Design doc, peer review | Weekly sync | Integration tests, two reviewers |
| 3 | Design review, cross-team input | Active mentorship, milestone gates | SLO/SLI defined, architecture sign-off |
| 4 | Architecture review, stakeholder alignment | Steering committee, risk reviews | Threat model, security review |
| 5 | Governance board, multi-org consensus | Governance cadence, multi-year planning | Multi-org review, migration plan |

## The Senior Inflection Point

Entry and Junior tiers focus on execution quality: delivering working code, following standards, building technical depth. Senior and above shift to leadership: scope of impact, creating clarity for others, making the right trade-offs under ambiguity.

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
| Decision-Making | Second Order Thinking | Tech Debt Quadrant | Cynefin, Rumsfeld Matrix | OODA Loop, Pre-Mortems | Wardley Mapping |
| Legacy Systems | Chesterton's Fence | Boy Scout Rule | Strangler Fig | Migration Planning | Lindy Effect |
| Reliability | Observability Pillars | Resilience Patterns | SLO/SLI/SLA, Error Budgets | Chaos Engineering | Platform Strategy |
| Design | Code Qualities, SOLID | Common Patterns | CVA, GoF Wisdom | Design Principles | Governance Frameworks |

## Planning Usage

When classifying a task during planning:

1. Identify the tier based on scope, risk, and required experience
2. Set design review rigor to match the tier
3. Select patterns appropriate for that tier (avoid over-engineering lower tiers)
4. Define quality gates that match the tier's expectations
5. Assign oversight level proportional to complexity
