# Gemini Code Assist: styleguide.md Format

**Location**: `.gemini/styleguide.md` (repository root)

## Format Requirements

- Natural language Markdown (no strict schema)
- Extends standard review prompt
- Combined with group-level style guides (enterprise)

## Recommended Structure

```markdown
# [Project Name] Coding Style Guide

## Introduction
[High-level principles and philosophy]

## Language Standards
[Deviations from PEP 8, Google Style Guide, etc.]

## Code Organization
### Line Length
### Indentation
### Import Organization

## Naming Conventions
### Variables
### Constants
### Functions/Methods
### Classes
### Modules/Files

## Documentation
### Docstrings
### Type Hints
### Comments

## Code Patterns
### Error Handling
### Logging
### Asynchronous Code

## Tooling
### Required Tools
### Configuration

## Examples
### Good
### Avoid
```

## Default Review Categories (No Custom Style Guide)

1. **Correctness** - Logic errors, edge cases, race conditions
2. **Efficiency** - Performance, memory leaks, redundant calculations
3. **Maintainability** - Readability, modularity, naming, documentation
4. **Security** - Vulnerabilities, injection attacks, access controls
5. **Miscellaneous** - Testing, scalability, error logging

## Effective Style Guides

- Specific and actionable rules
- Code examples for clarity
- Rationale for non-obvious rules
- Links to external standards
- Concise (avoid wall of text)

## Avoid

- Restating language defaults without deviation
- Vague principles without concrete rules
- Overly prescriptive micro-management
- Conflicting guidance
- Content longer than actual code
