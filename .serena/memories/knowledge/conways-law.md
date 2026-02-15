# Conway's Law

**Created**: 2026-01-10
**Category**: Mental Models / Organization Design

## The Law

"Organizations which design systems are constrained to produce designs which are copies of the communication structures of these organizations."

**Attribution**: Melvin Conway, 1967

## Core Insight

Technical architecture mirrors organizational structure. Communication is easier within boundaries than across them, so systems develop boundaries that match team boundaries.

## The Inverse Conway Maneuver

Deliberately restructure teams to produce desired architecture:

- Want microservices? Create small, autonomous teams with end-to-end ownership
- Want modular monolith? Align teams with modules
- Want bounded contexts? Match teams to domains

## Application to This Project

**Agent system design**:

- Agent specialization reflects role boundaries
- Handoff protocols mirror inter-agent communication
- Skill organization reflects capability groupings

**Implications for contributors**:

- Single-contributor projects have simpler architectures
- Multi-contributor projects need explicit boundaries
- Remote/async teams need explicit integration points

## Warning Signs

- Architecture doesn't match team structure (friction)
- Teams need frequent cross-boundary coordination (coupling)
- No clear ownership of components (diffuse responsibility)

## Related

- [foundational-knowledge-index](foundational-knowledge-index.md): Overview
- Bounded Contexts (DDD): Align contexts with teams
- `.agents/analysis/foundational-engineering-knowledge.md`: Full context
