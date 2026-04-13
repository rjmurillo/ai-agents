# Antifragility

**Category**: System Design
**Source**: `.agents/analysis/senior-engineering-knowledge.md`
**Origin**: Nassim Nicholas Taleb

## Core Concept

Design things that improve with stress/chaos.

## Three Categories

| Category | Definition | Example |
|----------|------------|---------|
| **Fragile** | Harmed by volatility | Monoliths, single points of failure |
| **Robust** | Unchanged by volatility | Redundancy, fallbacks |
| **Antifragile** | Improved by volatility | Learning systems, chaos engineering |

## Software Applications

| Practice | How It's Antifragile |
|----------|----------------------|
| Chaos engineering | Controlled failures improve resilience |
| Blameless postmortems | Incidents improve knowledge |
| A/B testing | User behavior improves product |
| Continuous improvement | Process stress improves process |
| Feature toggles | Quick recovery improves confidence |

## Building Antifragile Systems

1. **Embrace small failures**: Fail fast, learn fast
2. **Build optionality**: Multiple paths to success
3. **Limit downside**: Circuit breakers, bulkheads
4. **Capture upside**: Learn from every incident
5. **Decentralize**: Avoid single points of failure

## Anti-Pattern

Over-optimization for known scenarios creates fragility to unknown scenarios.

## Related

- [resilience-patterns](resilience-patterns.md) - Circuit breaker, bulkhead
- [cynefin-framework](cynefin-framework.md) - Complex problem handling
