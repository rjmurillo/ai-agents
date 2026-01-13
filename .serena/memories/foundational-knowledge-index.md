# Foundational Software Engineer Knowledge Index

**Purpose**: Index of essential software engineering knowledge for engineers with less than 5 years experience.
**Comprehensive Index**: [engineering-knowledge-index](engineering-knowledge-index.md)

## Knowledge Categories

### Mindsets & Mental Models
- **Chesterton's Fence**: Understand before removing
- **Hyrum's Law**: All observable behavior becomes dependency
- **Conway's Law**: Systems mirror organization structure
- **Second-Order Thinking**: Consider downstream consequences
- **Law of Demeter**: Only talk to immediate friends
- **Gall's Law**: Complex systems evolve from simple ones
- **YAGNI**: Don't build until needed
- **Technical Debt Quadrant**: Classify debt by intent/prudence
- **Boy Scout Rule**: Leave code better than found

### Software Principles
- **SOLID**: SRP, OCP, LSP, ISP, DIP
- **DRY**: One source of truth
- **KISS**: Keep it simple
- **Separation of Concerns**: One responsibility per module
- **Tell Don't Ask**: Co-locate behavior with data
- **Programming by Intention**: Express intent over implementation
- **Design to Interfaces**: Depend on abstractions

### Practices & Disciplines
- **TDD**: Red-green-refactor cycle
- **Pair Programming**: Driver/navigator collaboration
- **Code Reviews**: Knowledge transfer and defect detection
- **Refactoring**: Systematic improvement via code smells catalog
- **Clean Architecture**: Domain-centric, infrastructure-isolated
- **12-Factor App**: Cloud-ready application methodology
- **Trunk-Based Development**: Small, frequent commits to main
- **Observability**: Logs, metrics, traces

### Tradeoffs & Patterns
- **CAP Theorem**: Consistency, Availability, Partition Tolerance
- **Design Patterns**: Strategy, Factory, Decorator, Adapter, Composite, Observer, Null Object

### Security
- **OWASP Top 10**: Critical web vulnerabilities
- **Least Privilege**: Minimal permissions, reduced blast radius

### Architecture
- **C4 Model**: Context, Container, Component, Code
- **Circuit Breaker**: Fail-fast resilience pattern
- **Strangler Fig**: Incremental legacy modernization
- **Event-Driven Architecture**: Pub-sub, CQRS, event sourcing

### Thinking Models
- **Wardley Mapping**: Evolution axis for technology strategy
- **Cynefin Framework**: Clear, Complicated, Complex, Chaotic
- **Antifragility**: Systems that improve from stress
- **Rumsfeld Matrix**: Known/unknown uncertainty classification

### Team & Organization
- **SRE**: Operations as software problem
- **Team Topologies**: Stream-aligned, Platform, Enabling, Complicated-subsystem

## Related Knowledge Sets

| Experience Level | Memory Index |
|------------------|--------------|
| Foundational (< 5 yrs) | [foundational-knowledge-index](foundational-knowledge-index.md) (this file) |
| All Tiers (Comprehensive) | [engineering-knowledge-index](engineering-knowledge-index.md) |
| Principal (15+ yrs) | [principal-engineering-knowledge](principal-engineering-knowledge.md) |
| Distinguished (25+ yrs) | [distinguished-engineer-knowledge-index](distinguished-engineer-knowledge-index.md) |

## Cross-References
- Security: [security-principles-owasp](security-principles-owasp.md)
- Architecture: [c4-model](c4-model.md), [strangler-fig-pattern](strangler-fig-pattern.md)
- Thinking: [cynefin-framework](cynefin-framework.md), [antifragility](antifragility.md), [wardley-mapping](wardley-mapping.md)
- Principles: [yagni-principle](yagni-principle.md), [boy-scout-rule](boy-scout-rule.md), [law-of-demeter](law-of-demeter.md)