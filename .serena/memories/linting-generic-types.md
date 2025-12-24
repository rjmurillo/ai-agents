# Skill-Lint-007: Escape Generic Types as Inline Code

**Statement**: Wrap .NET generic types in backticks to prevent MD033 inline HTML violations

**Context**: C# documentation with generic types

**Atomicity**: 95%

**Impact**: 8/10

## Problem

Bare generic types like `ArrayPool<T>` trigger MD033 inline HTML violations because `<T>` looks like HTML.

## Solution

Use backticks: `ArrayPool<T>` instead of bare generic types.

## Examples

| Wrong | Correct |
|-------|---------|
| List<string> | `List<string>` |
| Dictionary<K,V> | `Dictionary<K,V>` |
| Func<T, TResult> | `Func<T, TResult>` |

## Related

- Skill-Lint-006 for code blocks
- MD033 rule explanation
