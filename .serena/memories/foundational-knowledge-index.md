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

## Related

- Full analysis: `.agents/analysis/foundational-engineering-knowledge.md`
- Chesterton integration: `chestertons-fence-memory-integration`
- Design approaches: `design-approaches-detailed`
- ADR concepts: `adr-foundational-concepts`
