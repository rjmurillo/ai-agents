---
name: Testing Approach
applyTo: "**/*.Tests.ps1"
priority: 7
version: 0.1.0
status: placeholder
---

# Testing Approach Steering

**Status**: Placeholder for Phase 4 implementation

## Scope

**Applies to**: 
- `**/*.Tests.ps1` - Pester test files

## Purpose

This steering file will provide Pester testing conventions and patterns.

## Planned Content (Phase 4)

### Guidelines
- Pester 5.x conventions
- Test naming patterns (Describe/Context/It)
- AAA pattern (Arrange, Act, Assert)
- Test isolation
- Coverage expectations (≥80%)

### Patterns
- Describe/Context/It structure
- BeforeAll/BeforeEach setup
- Mock usage with Pester
- Parameter validation testing
- Pipeline testing

### Anti-Patterns
- Test interdependencies
- Testing implementation details
- Fragile tests
- Missing assertions
- Overly complex tests

### Examples
- Well-structured Pester tests
- Mock scenarios
- Parameter validation tests

---

*This is a placeholder file. Content will be added in Phase 4: Steering Scoping*
