---
source: wiki/concepts/Engineering Concepts.md
created: 2026-04-11
review-by: 2026-07-11
---

# Engineering Complexity Tiers

<<<<<<< Updated upstream
Five tiers of engineering difficulty mapped to experience levels and focus areas. Use for milestone design, task decomposition, and review gate calibration.
||||||| Stash base
Five tiers of engineering difficulty mapped to IC levels and MSec SWE expectations. Use for task classification, design review rigor, and quality gate depth.
=======
Five tiers of engineering difficulty mapped to industry-standard experience levels. Use for milestone design, task decomposition, and review gate calibration.
>>>>>>> Stashed changes

## Tier Summary

<<<<<<< Updated upstream
| Tier | Level | Focus | Autonomy |
|------|-------|-------|----------|
| 1 | Entry (<2 years) | Pre-defined, scoped punch list items. Clear inputs and outputs. | Low. Tasks are assigned with explicit acceptance criteria. |
| 2 | Junior (2-5 years) | More autonomy, broader scope. Owns features within a defined boundary. | Moderate. Can make implementation decisions within constraints. |
| 3 | Senior (5-10 years) | Complex, multi-component problems. Trade-offs, operability, evolution. | High. Defines approach, identifies risks, mentors others. |
| 4 | Staff (10-15 years) | Complex, risky, strategic problems. Brings clarity to ambiguous situations. | Very high. Sets technical direction for a product or domain. |
| 5 | Principal (15+ years) | Governance, legacy, organizational clarity. Brings clarity to groups, not just products. | Full. Shapes engineering culture and multi-year technical strategy. |
||||||| Stash base
| Tier | IC Levels | Focus | Complexity |
|------|-----------|-------|------------|
| 1 | IC59-IC60 | Mental models, principles, practices | Simple, component-level |
| 2 | IC61-IC62 | Architecture, patterns, cross-team | Moderate, feature-level |
| 3 | IC63-IC64 | Trade-offs, evolution, operability | Complex, multi-team |
| 4 | IC65-IC67 | Strategy, risk, organizational leadership | Complex, risky, strategic |
| 5 | IC68+ | Legacy thinking, governance, time horizons | Governance and legacy |
=======
| Tier | Level | Task Profile | Autonomy |
|------|-------|-------------|----------|
| 1 | Entry / Junior (0-3 years) | Pre-defined, scoped punch list items. Clear inputs, expected outputs. | Low. Tasks assigned with explicit acceptance criteria. |
| 2 | Mid-Level (3-5 years) | Owns features end-to-end within a defined boundary. Moderate ambiguity. | Moderate. Makes implementation decisions, asks when stuck. |
| 3 | Senior (5-8 years) | Complex, poorly-defined problems. Pushes back on requirements. Mentors others. | High. Defines approach, identifies risks, mentors juniors. |
| 4 | Staff (8-12 years) | Resolves ambiguity for a team or domain. Brings clarity to products and individuals. | Very high. Sets technical direction for a domain. |
| 5 | Principal (12+ years) | Brings clarity to groups, not just products. Sets direction across multiple orgs. | Full. Shapes engineering culture and company-wide strategy. |
>>>>>>> Stashed changes

<<<<<<< Updated upstream
## Planning Implications
||||||| Stash base
## Before Work: Task Classification
=======
## The Inflection Point: Senior to Staff
>>>>>>> Stashed changes

<<<<<<< Updated upstream
| Tier | Milestone Design | Decomposition Style |
|------|-----------------|---------------------|
| 1 | Batch into larger milestones. Each task has explicit done criteria. | Punch list. Each item is self-contained with clear inputs/outputs. |
| 2 | Feature-level milestones. Design doc required. | Feature breakdown. Owner decides implementation within boundaries. |
| 3 | Independent milestones with design review gates. | Risk-based decomposition. Owner identifies approach and risks. |
| 4 | Proof-of-concept milestone first. ADR required. Stakeholder alignment. | Strategic decomposition with explicit rollback plans per milestone. |
| 5 | Governance milestone with multi-org consensus. Multi-year horizon. | Evolutionary decomposition. Each increment must deliver standalone value. |
||||||| Stash base
| Tier | Design Review Rigor | Reviewer Profile |
|------|-------------------|------------------|
| 1 | Self-review, code review | Any team member |
| 2 | Design doc, peer review | Senior engineer |
| 3 | Design review, cross-team input | Principal or architect |
| 4 | Architecture review, stakeholder alignment | Distinguished or VP-level |
| 5 | Governance board, multi-org consensus | Organization leadership |
=======
Senior to Staff is where execution stops being the primary measure of value. A Senior's output is code. A Staff's output is decisions, clarity, and team unblocking.
>>>>>>> Stashed changes

<<<<<<< Updated upstream
## Review Gate Calibration
||||||| Stash base
## During Work: Patterns and Oversight
=======
Staff engineers work in the white space between teams (Larson). Senior engineers solve problems handed to them. Staff engineers identify which problems matter.
>>>>>>> Stashed changes

<<<<<<< Updated upstream
| Tier | Before Work | During Work | After Work |
|------|-------------|-------------|------------|
| 1 | Self-review, code review | Async review | Unit tests, single reviewer |
| 2 | Design doc, peer review | Weekly sync | Integration tests, two reviewers |
| 3 | Design review, cross-team input | Active mentorship, milestone gates | SLO/SLI defined, architecture sign-off |
| 4 | Architecture review, stakeholder alignment | Steering committee, risk reviews | Threat model, security review |
| 5 | Governance board, multi-org consensus | Governance cadence, multi-year planning | Multi-org review, migration plan |
||||||| Stash base
| Tier | Appropriate Patterns | Oversight Level |
|------|---------------------|-----------------|
| 1 | SOLID, DRY, basic GoF patterns | Async code review |
| 2 | Resilience patterns, cross-service design | Weekly sync, design doc |
| 3 | CVA, GoF wisdom, strangler fig, error budgets | Active mentorship, milestone gates |
| 4 | OODA loop, pre-mortems, chaos engineering | Steering committee, risk reviews |
| 5 | Lindy effect, second system effect, path dependence | Governance cadence, multi-year planning |
=======
## Planning Implications
>>>>>>> Stashed changes

<<<<<<< Updated upstream
## The Senior Inflection Point
||||||| Stash base
## After Work: Quality Gates
=======
| Tier | Milestone Design | Decomposition Style |
|------|-----------------|---------------------|
| 1 | Batch into larger milestones. Each task has explicit done criteria. | Punch list. Each item is self-contained. |
| 2 | Feature-level milestones. Design doc required. | Feature breakdown. Owner decides implementation. |
| 3 | Independent milestones with design review gates. | Risk-based decomposition. Owner defines approach. |
| 4 | Proof-of-concept milestone first. ADR required. Stakeholder alignment. | Strategic decomposition with rollback plans per milestone. |
| 5 | Governance milestone with multi-org consensus. Multi-year horizon. | Evolutionary decomposition. Each increment delivers standalone value. |
>>>>>>> Stashed changes

<<<<<<< Updated upstream
Entry and Junior tiers focus on execution quality: delivering working code, following standards, building technical depth. Senior and above shift to leadership: scope of impact, creating clarity for others, making the right trade-offs under ambiguity.
||||||| Stash base
| Tier | Quality Gate | Review Depth |
|------|-------------|--------------|
| 1 | Unit tests pass, code review approved | Single reviewer |
| 2 | Integration tests, design doc updated | Two reviewers, cross-team ack |
| 3 | SLO/SLI defined, operational readiness | Architecture sign-off, load test |
| 4 | Threat model, chaos experiment results | Security review, exec sign-off |
| 5 | Governance approval, deprecation plan | Multi-org review, migration plan |
=======
## Review Gate Calibration
>>>>>>> Stashed changes

<<<<<<< Updated upstream
Tier 3 is where engineers stop being measured on what they build and start being measured on what they enable others to build.
||||||| Stash base
## IC63 Inflection Point

IC59-IC62 categories focus on execution quality (Business Impact, Design and Delivery, Technical Excellence). IC63+ shifts to leadership categories (Scope of Impact, Leadership, Create Clarity, Generate Energy, Deliver Success, Role Model).

Tier 3 concepts develop the capabilities that differentiate Senior from IC62.

## MSec Categories by Tier

| Tier | MSec Categories |
|------|----------------|
| 1-2 | Business Impact, Execution and Planning, Design and Delivery, Technical Excellence |
| 2 | adds Collaboration and Support |
| 3+ | Scope of Impact, Leadership, Create Clarity, Generate Energy, Deliver Success, Role Model |
=======
| Tier | Before Work | During Work | After Work |
|------|-------------|-------------|------------|
| 1 | Self-review, code review | Async review, pairing | Unit tests, single reviewer |
| 2 | Design doc, peer review | Weekly sync | Integration tests, two reviewers |
| 3 | Design review, cross-team input | Active mentorship, milestone gates | SLO/SLI defined, architecture sign-off |
| 4 | Architecture review, stakeholder alignment | Steering committee, risk reviews | Threat model, security review |
| 5 | Governance board, multi-org consensus | Governance cadence, multi-year planning | Multi-org review, migration plan |

## Staff vs Principal in Practice

| Dimension | Staff | Principal |
|-----------|-------|-----------|
| Scope | One org, one domain | Multiple orgs, whole company |
| Ambiguity target | Clarifies a team's direction | Clarifies direction across groups |
| Influence | Peer teams | Org-wide or company-wide |
| Code contribution | Significant | Strategic |
>>>>>>> Stashed changes

## Problem Domain Cross-Reference

<<<<<<< Updated upstream
| Domain | Tier 1 (Entry) | Tier 2 (Junior) | Tier 3 (Senior) | Tier 4 (Staff) | Tier 5 (Principal) |
|--------|----------------|-----------------|-----------------|----------------|-------------------|
||||||| Stash base
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
=======
| Domain | Tier 1 (Entry/Junior) | Tier 2 (Mid) | Tier 3 (Senior) | Tier 4 (Staff) | Tier 5 (Principal) |
|--------|----------------------|--------------|-----------------|----------------|-------------------|
>>>>>>> Stashed changes
| Decision-Making | Second Order Thinking | Tech Debt Quadrant | Cynefin, Rumsfeld Matrix | OODA Loop, Pre-Mortems | Wardley Mapping |
| Legacy Systems | Chesterton's Fence | Boy Scout Rule | Strangler Fig | Migration Planning | Lindy Effect |
| Reliability | Observability Pillars | Resilience Patterns | SLO/SLI/SLA, Error Budgets | Chaos Engineering | Platform Strategy |
| Design | Code Qualities, SOLID | Common Patterns | CVA, GoF Wisdom | Design Principles | Governance Frameworks |
