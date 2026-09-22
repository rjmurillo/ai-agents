# Domain-Driven Design: Event Storming

**Category**: Domain Modeling
**Source**: `.agents/analysis/advanced-engineering-knowledge.md`
**Origin**: Alberto Brandolini

## Core Concepts

| Concept | Definition |
|---------|------------|
| Ubiquitous Language | Domain experts and developers use same terms |
| Bounded Context | Each domain model lives in clear boundary |
| Aggregate | Cluster of objects treated as unit for changes |
| Entity | Object with identity persisting across changes |
| Value Object | Object defined by attributes, interchangeable |
| Domain Event | Something that happened domain experts care about |
| Anti-Corruption Layer | Translation protecting domain from external models |

## Event Storming Process

1. Gather domain experts and developers
2. Write domain events on orange sticky notes
3. Sequence events on timeline
4. Identify commands that trigger events (blue)
5. Identify aggregates that handle commands (yellow)
6. Draw context boundaries

## Output

- Shared understanding
- Bounded context map
- Event catalog

## Context Mapping Patterns

| Pattern | Description |
|---------|-------------|
| Shared Kernel | Two contexts share subset of model |
| Customer-Supplier | Upstream serves downstream |
| Conformist | Downstream conforms to upstream |
| Anti-Corruption Layer | Downstream translates from upstream |
| Open Host Service | Upstream provides integration protocol |
| Published Language | Shared language for integration |

## Related

- `bounded-contexts` - Context boundaries
- `architecture-producer-consumer` - Event patterns
