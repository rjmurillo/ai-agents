---
source: wiki/concepts/Mental Models/Conways Law.md
created: 2026-05-31
review-by: 2026-08-31
---

# Conway's Law

## Principle

Organizations design systems that mirror their own communication structure.

> "Any organization that designs a system will produce a design whose structure is a copy of the organization's communication structure." -- Melvin Conway

## Corollary

The inverse maneuver (the "inverse Conway maneuver") is to shape the team structure first so the desired architecture becomes the path of least resistance. If two modules must talk, the teams behind them must talk; if you want a clean boundary, put a team boundary there.

## Decision Critic Application

Use this model during **Challenge** (Steps 5-6) when a decision proposes a module boundary, a service split, or an ownership change, and especially when the diff crosses a module boundary.

### Verification Questions

When a decision proposes an architecture or a boundary:

1. Which team owns each side of the proposed boundary?
2. Does the communication structure of the org match the proposed system structure?
3. If two components must integrate, do the teams behind them actually talk?
4. Is the boundary being drawn for technical reasons, or to match a reporting line?

### Red Flags in Decisions

| Signal | Risk |
|--------|------|
| "Each team owns its own service" | Boundaries follow the org chart, not the domain |
| "We'll integrate these later" | The teams do not communicate, so the seam will leak |
| "This module is shared across three teams" | No single owner; change amplification across teams |
| "Reorg first, then re-architect" | Architecture will snap back to the new org shape |
| Diff crosses a module boundary owned by another team | Hidden coordination cost; integration mismatch |

### Contrarian Perspectives (Step 5)

When reviewing boundary and ownership decisions, generate these contrarian views:

- "What if the proposed module split just encodes the current org chart instead of the domain?"
- "What if we changed the team structure first and let the architecture follow?"
- "Which seam will leak because the two teams behind it never talk?"

### Failure Modes (for Inversion Analysis)

- A clean architecture erodes because the org structure pulls it back toward the reporting lines
- Integration defects cluster at boundaries between teams that do not communicate
- A shared module becomes a coordination bottleneck no single team owns
- A reorg silently invalidates an architecture that depended on the old communication paths

## Practical Checklist

Before accepting a boundary or ownership decision as VERIFIED:

- [ ] Owner identified for each side of every proposed boundary
- [ ] Communication paths between owning teams exist where components must integrate
- [ ] Boundary justified by the domain, not only by the org chart
- [ ] Coordination cost of any cross-team boundary acknowledged

## Related Models

- Gall's Law: complex systems evolve from simple working systems
- Chesterton's Fence: understand an existing boundary before moving it
- Systems Thinking: a boundary change is a system change with second-order effects
