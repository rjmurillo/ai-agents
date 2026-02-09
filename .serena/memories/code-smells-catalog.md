# Code Smells Catalog

**Category**: Code Quality
**Source**: Mäntylä Taxonomy, Martin Fowler, SonarSource, Marcel Jerzyk

## Core Concept

Code smells are surface indicators of deeper design problems. They are not bugs, the code still works, but they signal refactoring opportunities. Kent Beck coined the term during work on Fowler's Refactoring book (1999).

## The Mäntylä Taxonomy (Five Categories)

### 1. Bloaters (Code Grown Too Large)

| Smell | Signal | Fix |
|-------|--------|-----|
| Long Method | >15 lines | Extract Method |
| Large Class | >200 lines, >5 fields | Extract Class |
| Primitive Obsession | Strings/ints for domain concepts | Introduce Value Objects |
| Long Parameter List | >4 parameters | Parameter Object |
| Data Clumps | Same 3+ fields repeated | Extract Class |

### 2. Object-Orientation Abusers

| Smell | Signal | Fix |
|-------|--------|-----|
| Switch Statements | Type-checking for behavior | Replace with Polymorphism |
| Temporary Field | Field only set sometimes | Extract Class, Null Object |
| Refused Bequest | Unused inherited methods | Replace Inheritance with Delegation |
| Alternative Classes Different Interfaces | Same job, different signatures | Extract Superclass |

### 3. Change Preventers

| Smell | Signal | Fix |
|-------|--------|-----|
| Divergent Change | One class, multiple change reasons | Extract Class |
| Shotgun Surgery | One change touches many files | Move Method, Inline Class |
| Parallel Inheritance | Subclass in A requires subclass in B | Collapse hierarchy |

### 4. Dispensables

| Smell | Signal | Fix |
|-------|--------|-----|
| Comments | "What" not "why" | Extract Method, Rename |
| Duplicate Code | Same structure repeated | Extract Method, Pull Up |
| Lazy Class | Doesn't justify existence | Inline Class |
| Data Class | Only getters/setters | Move Method to data |
| Dead Code | Never executed | Delete |
| Speculative Generality | For future needs that didn't come | Inline, Collapse |

### 5. Couplers

| Smell | Signal | Fix |
|-------|--------|-----|
| Feature Envy | Uses other class's data more than own | Move Method |
| Inappropriate Intimacy | Classes share too much | Move Method/Field |
| Message Chains | a.getB().getC().getD() | Hide Delegate |
| Middle Man | Delegates everything | Remove Middle Man |

## Smell-to-Refactoring Quick Map

| Refactoring | Addresses |
|-------------|-----------|
| Extract Method | Long Method, Duplicate Code, Feature Envy, Comments |
| Move Method | Feature Envy, Shotgun Surgery, Message Chains |
| Extract Class | Large Class, Data Clumps, Divergent Change |
| Replace Conditional with Polymorphism | Switch Statements |

## Detection Questions

1. **Readability**: Does this code explain itself?
2. **Change Impact**: Is change isolated or scattered?
3. **Testability**: Is this easy to test?
4. **Extensibility**: Can I add features without modification?

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

## Severity Levels

| Level | Action |
|-------|--------|
| BLOCKER | Fix immediately, blocks merge |
| CRITICAL | Fix before release |
| MAJOR | Fix in next sprint |
| MINOR | Fix opportunistically |

## Related

- [refactoring-001-delete-over-extract](refactoring-001-delete-over-extract.md)
- [law-of-demeter](law-of-demeter.md)
- [design-by-contract](design-by-contract.md)
- Full analysis: `.agents/analysis/code-smells-comprehensive-catalog.md`
