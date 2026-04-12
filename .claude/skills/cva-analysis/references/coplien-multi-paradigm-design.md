---
source: wiki/concepts/Design Principles/Commonality Variability Analysis.md
created: 2026-04-11
review-by: 2026-07-11
---

# Coplien's Multi-Paradigm Design

James O. Coplien's framework for using CVA as the foundation of software design.
From "Multi-Paradigm Design for C++" (1999).

## Core Thesis

Commonality analysis discovers the natural abstractions in a domain. Variability
analysis discovers how those abstractions differ. The relationship between
commonalities and variabilities determines which design patterns emerge.

## Key Quotes

"Commonality analysis is the search for common elements that helps us understand
how family members are the same."

"In design, our greatest vulnerability is often a wrong or missing abstraction."

## The CVA-to-Pattern Pipeline

```
Requirements → Commonalities → Variabilities → Relationships → Patterns
     |              |               |               |              |
  Problem        Nouns become    Concrete        How they       Strategy,
  domain         abstract types  implementations relate         Bridge,
                                                                Factory
```

## Rules

1. **Commonalities first.** They define the domain concepts. Without them,
   variabilities have no frame of reference.
2. **Limit to "is-a" first.** Build confidence in entity relationships before
   exploring has-a, uses, or creates relationships.
3. **Nouns from CVA become abstract types.** The matrix rows name your
   abstractions. The matrix cells name your concrete implementations.
4. **Rows map to Strategies.** Each row is a family of algorithms that can be
   encapsulated and made interchangeable.
5. **Columns map to Factories.** Each column is a family of related objects
   that must be created together. Abstract Factory ensures only valid
   combinations are built.

## Relationship to GoF

| CVA Element | GoF Pattern | When |
|---|---|---|
| Row (varying behavior) | Strategy | Always. Every row is a Strategy candidate. |
| Column (related family) | Abstract Factory | When column items are co-dependent. |
| Cross-cutting concern | Bridge | When two independent hierarchies interact. |
| Object creation | Factory Method | When subclasses decide which class to instantiate. |
| Wrapper needed | Adapter/Facade | When existing code must match a new interface. |

## Common Mistakes

- **Premature abstraction**: Creating abstractions before finding commonalities
  in actual requirements. CVA prevents this by requiring concrete cases first.
- **Mixing perspectives**: Conceptual, specification, and implementation concerns
  in the same analysis. Keep them separate (Fowler's three perspectives).
- **Ignoring empty cells**: Empty cells in the CVA matrix are questions, not
  gaps. They reveal missing requirements or invalid combinations.

## Further Reading

- Coplien, J. (1999). Multi-Paradigm Design for C++. Addison-Wesley.
- Gamma et al. (1994). Design Patterns. Addison-Wesley.
- Alexander, C. (1979). The Timeless Way of Building. Oxford University Press.
