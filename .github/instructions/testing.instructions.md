applyTo: "**/*.test.*,**/*.spec.*"

# Testing Standards

Write comprehensive, maintainable tests following xUnit conventions.

## Key Principles

- **AAA Pattern**: Arrange, Act, Assert
- **Isolation**: Each test is independent
- **Naming**: Descriptive test names that explain the scenario
- **Coverage**: Target ≥80% code coverage for new code
- **Fast**: Keep unit tests fast (<100ms each)

## Test Structure

```csharp
[Fact]
public void MethodName_Scenario_ExpectedBehavior()
{
    // Arrange
    var sut = new SystemUnderTest();
    
    // Act
    var result = sut.DoSomething();
    
    // Assert
    Assert.NotNull(result);
}
```

## Mocking

- Use Moq for interface mocking
- Mock external dependencies (HTTP, database, etc.)
- Verify important interactions
- Don't over-mock - test behavior, not implementation

## Anti-Patterns to Avoid

- ❌ Test interdependencies
- ❌ Testing implementation details
- ❌ Fragile assertions (specific strings, order)
- ❌ Missing assertions
- ❌ Overly complex test setup

*Note: Full steering content to be implemented in Phase 4. See `.agents/steering/testing-approach.md` for placeholder.*
