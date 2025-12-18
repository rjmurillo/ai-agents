applyTo: "**/*.cs"

# C# Coding Standards

Follow SOLID principles and established C# patterns for all C# code.

## Key Principles

- **Async/await**: Use async methods consistently, never block on async calls
- **Naming**: PascalCase for public members, camelCase for private/local
- **Null handling**: Use nullable reference types, validate parameters
- **Exception handling**: Use specific exception types, don't swallow exceptions
- **Dependency injection**: Use constructor injection for dependencies
- **Performance**: Avoid allocations in hot paths, use value types appropriately

## Patterns

- **Repository pattern**: For data access abstraction
- **Service layer**: For business logic orchestration
- **Configuration**: Use IOptions pattern for settings

## Anti-Patterns to Avoid

- ❌ Sync over async (`.Result`, `.Wait()`)
- ❌ God classes with too many responsibilities
- ❌ Catching generic Exception without re-throwing
- ❌ Mutable shared state without synchronization
- ❌ Tight coupling to concrete implementations

## Testing

- Write unit tests for all business logic
- Target ≥80% code coverage
- Use AAA pattern (Arrange, Act, Assert)
- Mock external dependencies

*Note: Full steering content to be implemented in Phase 4. See `.agents/steering/csharp-patterns.md` for placeholder.*
