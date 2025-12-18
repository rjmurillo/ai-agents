---
applyTo: "**/*.Tests.ps1"
---

# Testing Standards

For comprehensive testing standards, see [.agents/steering/testing-approach.md](../../.agents/steering/testing-approach.md).

## Quick Reference - Pester Tests

**Structure:**

```powershell
Describe "FunctionName" {
    Context "When scenario" {
        It "Should behavior" {
            # Arrange, Act, Assert
        }
    }
}
```

**Key Principles:**

- AAA Pattern (Arrange, Act, Assert)
- Independent tests
- Descriptive names
- ≥80% coverage target
- Use `Mock` for dependencies

*This file serves as a Copilot-specific entry point. The authoritative steering content is maintained in `.agents/steering/testing-approach.md`.*
