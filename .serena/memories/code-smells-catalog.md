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

## Implementation Smells

These patterns are caught by the code-simplifier agent. Avoid them during implementation.

| Smell | Signal | Fix |
|-------|--------|-----|
| Stderr Suppression | `2>/dev/null`, `-ErrorAction SilentlyContinue` | Capture output to variable, check, then act |
| Repeated Block | 3+ identical lines in 2+ locations | Extract function or use loop |
| Dead Variable | Variable assigned but never read | Remove assignment |
| Redundant Condition | `if (x) { return true } else { return false }` | Return `x` directly |
| Inconsistent Naming | `camelCase` in a `snake_case` file | Match file convention |
| Deep Nesting | 3+ levels of if/for/while | Early return, guard clause, or extract |
| Unquoted Expansion | `$var` in bash without quotes | Quote: `"$var"` or use array |
| Silent Failure | catch/except with no logging or rethrow | Log error or propagate |
| Hardcoded Path | Absolute paths in scripts | Use variables or `$PSScriptRoot` |
| Pattern Mismatch | New error handling style in old module | Read existing patterns first |

## Detection Questions (Extended)

5. **Simplify**: Can this code be shorter without losing clarity?
6. **Suppress**: Am I hiding errors from the user or logs?
7. **Repeat**: Have I written this logic elsewhere in this PR?
8. **Name**: Would a reader know what this variable means without context?

## Application

Use as refactoring triggers during code review and maintenance.

## Related

- [refactoring-001-delete-over-extract](refactoring-001-delete-over-extract.md) - Refactoring approach
- [law-of-demeter](law-of-demeter.md) - Coupling concerns
