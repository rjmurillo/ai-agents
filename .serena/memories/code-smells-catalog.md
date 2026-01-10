# Code Smells Catalog

**Category**: Code Quality
**Source**: `.agents/analysis/advanced-engineering-knowledge.md`

## Core Concept

Code smells are surface indicators of deeper design problems. Not bugs, but refactoring opportunities.

## Smell Reference

| Smell | Signal | Fix |
|-------|--------|-----|
| God Class | Class does too much | Break into SRP classes |
| Feature Envy | Method uses another class's data excessively | Move behavior to data |
| Primitive Obsession | Using strings/ints instead of domain types | Introduce Value Objects |
| Shotgun Surgery | One change requires changes in many places | Centralize related behavior |
| Lava Flow | Dead but scary-to-remove code | Understand intent, test, remove |
| Magic Numbers/Strings | Literal values with unclear meaning | Use constants or enums |
| Switch Statements | Used for behavior control | Replace with polymorphism |

## Detection Questions

1. **Review**: Does this code explain itself?
2. **Change**: Is change isolated or scattered?
3. **Test**: Is this easy to test?
4. **Extend**: Can I add features without modification?

## Application

Use as refactoring triggers during code review and maintenance.

## Related

- `refactoring-001-delete-over-extract` - Refactoring approach
- `law-of-demeter` - Coupling concerns
