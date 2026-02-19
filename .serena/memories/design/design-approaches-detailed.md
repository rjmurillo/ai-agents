# Design Approaches (Detailed)

## Pattern-Oriented Development
Start with patterns in the problem, relate them in context. Patterns provide context for each other.

Design begins with recognizing recurring structures in the problem domain. Each pattern creates context that helps identify and refine other patterns.

## Commonality/Variability Analysis (CVA)

### Process
1. Start with commonalities in the problem domain
2. Then variabilities under them
3. Then relationships between them

### Greatest Vulnerability
Wrong or missing abstraction.

### CVA Matrix
- **Rows become Strategy patterns**: Each row represents a variation point
- **Columns become Abstract Factory**: Families of related objects that vary together
- **Open-closed principle**: New variations add factories, not modify existing code

### Example Application
When analyzing payment processing:
- **Commonality**: All payments need validation, processing, confirmation
- **Variabilities**: Credit card, PayPal, bank transfer (rows); US, EU, Asia regulations (columns)
- **Matrix**: 3x3 grid where each cell is a specific payment factory

## Emergent Design
Start with testability quality, refactor to open-closed, work up the hierarchy. For existing codebases.

### Process
1. Write tests first (or make code testable)
2. Refactor to open-closed principle
3. Work up the Software Hierarchy of Needs
4. Extract patterns as they emerge

### When to Use
- Legacy codebases without clear architecture
- Prototypes that need to evolve to production
- When requirements are unclear or changing rapidly

## Selection Criteria

| Situation | Recommended Approach |
|-----------|---------------------|
| Well-understood domain | Pattern-Oriented |
| Multiple variation points | CVA |
| Legacy code or unclear requirements | Emergent Design |
| New feature in existing system | Start with existing patterns, use CVA for new variations |

## Source
User preference: Richard Murillo's global CLAUDE.md (removed during token optimization 2026-01-04)

## Related

- [design-008-semantic-precision](design-008-semantic-precision.md)
- [design-by-contract](design-by-contract.md)
- [design-composability](design-composability.md)
- [design-diagrams](design-diagrams.md)
- [design-entry-criteria](design-entry-criteria.md)
