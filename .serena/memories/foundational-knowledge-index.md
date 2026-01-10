# Foundational Engineering Knowledge Index

**Created**: 2026-01-10
**Category**: Engineering Knowledge Management
**Source**: `.agents/analysis/foundational-engineering-knowledge.md`

## Purpose

Central index to foundational engineering knowledge covering mental models, principles, practices, and architectural patterns for thinking engineers.

## Mental Models (Decision Frameworks)

| Model | Memory File | Quick Reference |
|-------|-------------|-----------------|
| Chesterton's Fence | `chestertons-fence-memory-integration` | Search memory before changing |
| Hyrum's Law | `hyrums-law` | All observable behavior becomes contract |
| Conway's Law | `conways-law` | Teams mirror architecture |
| Second-Order Thinking | `second-order-thinking` | Ask "and then what?" |
| Law of Demeter | `law-of-demeter` | Only talk to friends |
| Gall's Law | `galls-law` | Start simple, evolve |
| YAGNI | `yagni-principle` | Build only what's needed now |
| Technical Debt Quadrant | `technical-debt-quadrant` | Prudent vs reckless, deliberate vs inadvertent |
| Boy Scout Rule | `boy-scout-rule` | Leave code cleaner |

## Engineering Principles

| Principle | Application |
|-----------|-------------|
| SOLID | Object-oriented design guidelines |
| DRY | Knowledge (not code) duplication |
| KISS | Simplest working solution |
| Separation of Concerns | Distinct responsibilities |
| Tell, Don't Ask | Push behavior to data owner |
| Programming by Intention | Top-down, declarative style |
| Design to Interfaces | Depend on abstractions |

## Practices

| Practice | When to Apply |
|----------|---------------|
| TDD | All new code (red-green-refactor) |
| Pair Programming | Knowledge transfer, complex problems |
| Code Reviews | Pre-merge validation |
| Refactoring | Small, continuous improvements |
| Clean Architecture | New systems requiring flexibility |
| 12-Factor | Cloud-native applications |
| Trunk-Based Dev | Continuous integration |
| Observability | Production systems (logs, metrics, traces) |

## Architecture Patterns

| Pattern | When to Use |
|---------|-------------|
| Hexagonal (Ports/Adapters) | Isolating core from infrastructure |
| Bounded Contexts (DDD) | Multiple domain models |
| Event-Driven | Loose coupling, scalability |
| CQRS | Read-heavy systems with complex writes |
| DORA Metrics | Measuring delivery performance |

## Self-Reflection Questions

Apply these before major decisions:

1. Why was this code written this way?
2. What's the real cost of this tech debt?
3. What will break if I change this?
4. What would I wish I had done differently in 3 months?
5. Can this be tested easily?
6. Is this over-engineered?
7. Can a junior engineer understand this?
8. Am I optimizing for today or imagined future?

## Distributed Systems (Advanced)

| Concept | Memory File | Quick Reference |
|---------|-------------|-----------------|
| CAP Theorem | `cap-theorem` | C, A, P: pick two |
| Resilience Patterns | `resilience-patterns` | Circuit breaker, bulkhead, retry |
| Backpressure | `backpressure-pattern` | Throttle upstream when downstream overwhelmed |
| Idempotency | `idempotency-pattern` | Safe to retry operations |

## Architecture Documentation (Advanced)

| Concept | Memory File | Quick Reference |
|---------|-------------|-----------------|
| C4 Model | `c4-model` | Context, Container, Component, Code |
| Poka-Yoke | `poka-yoke` | Make errors impossible or obvious |

## Software Craft (Advanced)

| Concept | Memory File | Quick Reference |
|---------|-------------|-----------------|
| Code Smells | `code-smells-catalog` | God Class, Feature Envy, etc. |
| Design Patterns | `design-patterns-usage-guide` | When to use, risks if misused |

## Security (Advanced)

| Concept | Memory File | Quick Reference |
|---------|-------------|-----------------|
| OWASP Principles | `security-principles-owasp` | Top 10, Least Privilege, Input Validation |

## Domain-Driven Design (Advanced)

| Concept | Memory File | Quick Reference |
|---------|-------------|-----------------|
| Event Storming | `ddd-event-storming` | Visual domain modeling technique |

## Engineering Culture (Advanced)

| Concept | Memory File | Quick Reference |
|---------|-------------|-----------------|
| Paved Roads | `paved-roads-innovation` | Default choices with deviation paths |
| Sociotechnical Systems | `sociotechnical-systems` | Tech and social intertwined |

## Senior Engineering Knowledge (Advanced)

| Concept | Memory File | Quick Reference |
|---------|-------------|-----------------|
| Tradeoff Thinking | `tradeoff-thinking` | Name tradeoffs explicitly |
| Design by Contract | `design-by-contract` | Preconditions, postconditions, invariants |
| Fallacies of Distributed Computing | `fallacies-distributed-computing` | Network is unreliable |
| Feature Toggles | `feature-toggles` | Decouple deploy from release |
| Strangler Fig Pattern | `strangler-fig-pattern` | Incremental migration |
| SLO/SLI/SLA | `slo-sli-sla` | Error budgets, reliability targets |
| Cynefin Framework | `cynefin-framework` | Clear, Complicated, Complex, Chaotic |
| Wardley Mapping | `wardley-mapping` | Innovate vs commoditize |
| Antifragility | `antifragility` | Improve with stress |
| Staff Engineer Trajectory | `staff-engineer-trajectory` | Career growth path |
| Engineering as Social Activity | `engineering-as-social-activity` | Writing, mentoring, cross-functional |

## Related

- Full analysis (Part 1): `.agents/analysis/foundational-engineering-knowledge.md`
- Full analysis (Part 2): `.agents/analysis/advanced-engineering-knowledge.md`
- Full analysis (Part 3): `.agents/analysis/senior-engineering-knowledge.md`
- Chesterton integration: `chestertons-fence-memory-integration`
- Design approaches: `design-approaches-detailed`
- ADR concepts: `adr-foundational-concepts`
