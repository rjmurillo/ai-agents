# Design Patterns Usage Guide

**Category**: Software Design
**Source**: `.agents/analysis/advanced-engineering-knowledge.md`

## Pattern Usage Matrix

| Pattern | Use When | Risk if Misused |
|---------|----------|-----------------|
| Strategy | Vary behavior at runtime | Overengineering if only 1 impl |
| Factory | Encapsulate complex creation | Obfuscation if creation simple |
| Decorator | Add behavior dynamically | Hard to trace with many layers |
| Adapter | Integrating incompatible interfaces | Unnecessary indirection |
| Null Object | Avoid null-checking everywhere | May hide real problems |
| Composite | Part-whole hierarchies | Overly complex trees |
| Observer/Event | Pub/sub decoupling | Temporal coupling, hard to trace |
| Specification | Encapsulate business rules | Overkill for simple predicates |

## Decision Checklist

Before applying a pattern:

1. Do I have the problem this pattern solves? (Not might have)
2. Is there a simpler solution?
3. Will future maintainers understand this?
4. Can I remove this pattern later if wrong?

## Anti-Patterns

- **Speculative generalization**: Patterns for imagined requirements
- **Golden hammer**: Using favorite pattern everywhere
- **Pattern mania**: Patterns for resume building
- **Cargo cult**: Copying patterns without understanding

## Related

- [code-smells-catalog](code-smells-catalog.md) - Detection of problems
- [yagni-principle](yagni-principle.md) - Build only what's needed
- [design-008-semantic-precision](design-008-semantic-precision.md)
- [design-approaches-detailed](design-approaches-detailed.md)
- [design-by-contract](design-by-contract.md)
- [design-composability](design-composability.md)
- [design-diagrams](design-diagrams.md)
