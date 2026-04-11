---
source: wiki/concepts/Design Principles/Wisdom from the Gang of Four.md, Pattern Oriented Design.md
created: 2026-04-11
review-by: 2026-07-11
---

# GoF Pattern Selection from CVA Results

After building a CVA matrix, use this guide to select the right GoF pattern
for each relationship discovered.

## Decision Table

| CVA Finding | Pattern | Rationale |
|---|---|---|
| Row with 2+ varying implementations | **Strategy** | Encapsulates a family of algorithms. Each row cell becomes a concrete strategy. |
| Column with co-dependent items | **Abstract Factory** | Builds only valid combinations. Each column becomes a concrete factory. |
| Two independent variation axes | **Bridge** | Decouples abstraction from implementation. Each axis varies independently. |
| Existing interface must match new abstraction | **Adapter** | Preserves existing interface while conforming to new abstraction. |
| Complex subsystem behind a CVA boundary | **Facade** | Simplifies access. The CVA boundary becomes the facade interface. |
| Object creation varies by context | **Factory Method** | Subclass decides which class to instantiate. |
| Row with identical cells (no variation) | **No pattern needed** | Remove from matrix. Make it a constant in the base class. |

## Pattern Ordering (instantiation is a late decision)

1. **Bridge** first (if two independent hierarchies exist)
2. **Strategy** next (one per varying row)
3. **Adapter/Facade** as needed (for legacy integration)
4. **Factory** last (creation depends on knowing what to create)

This ordering comes from Alexander's insight: "Before you can determine a good
way to create something, you need to know the nature of what you want to create."

## Three Perspectives (Fowler)

When analyzing CVA results, keep these separate:

| Perspective | Question | CVA Mapping |
|---|---|---|
| Conceptual | What do you want? | Matrix rows (abstractions) |
| Specification | What is the interface? | Strategy/Factory interfaces |
| Implementation | How is it coded? | Matrix cells (concrete classes) |

Mixing perspectives in the same analysis produces wrong abstractions.

## The Separate Use from Creation Rule

> A makes B, or A uses B. Never both.

When a CVA column produces a set of related objects:

- The **Factory** creates them (perspective of creation)
- The **client** uses them via interfaces (perspective of use)
- These are different classes. Never combine creation and use.

## Common Mistakes

| Mistake | CVA Signal | Fix |
|---|---|---|
| Premature Strategy | Row has only 1 cell filled | Wait for more cases before abstracting |
| Missing Factory | Column items created inline | Extract Factory to separate use from creation |
| Inheritance instead of delegation | "Is-a" used for specialization | Use Strategy (delegation) for varying behavior |
| N:M class relationships | Multiple rows reference each other | Introduce Bridge to decouple the hierarchies |
