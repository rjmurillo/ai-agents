# Poka-Yoke (Error-Proofing)

**Category**: Design Principle
**Source**: `.agents/analysis/advanced-engineering-knowledge.md`
**Origin**: Shigeo Shingo, Toyota Production System

## Core Principle

Design systems so errors are impossible or immediately obvious.

## Software Application

| Technique | Example |
|-----------|---------|
| Compile-time checks | Strong typing, exhaustive pattern matching |
| Constructor validation | Invalid objects cannot exist |
| Configuration validation | Fail fast on startup |
| API design | Required parameters, sensible defaults |
| UI design | Disable invalid actions, confirmation dialogs |

## Design for Inevitable Mistakes

1. Make invalid states unrepresentable
2. Validate at the boundary
3. Fail fast, fail loud
4. Prefer correctness over convenience

## Examples

**Wrong**: Accept nulls everywhere, check later
**Right**: Use non-nullable types, validate at construction

**Wrong**: Optional config values with runtime failures
**Right**: Required config with startup validation

## Related

- `security-002-input-validation-first` - Validate inputs
- `design-to-interfaces` - Contract enforcement
