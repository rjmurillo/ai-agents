# Design by Contract

<!-- doc-accuracy: external-sdk dotnet -- C# examples use the .NET base class library, not this repository -->

**Category**: Software Design
**Source**: `.project-toolkit/analysis/senior-engineering-knowledge.md`
**Origin**: Bertrand Meyer, Eiffel programming language

## Core Concept

Define input/output invariants clearly. Methods have:

- **Preconditions**: What must be true before calling
- **Postconditions**: What will be true after calling
- **Invariants**: What remains true throughout object lifetime

## Implementation

- Use type system to enforce constraints
- Validate at boundaries, trust internally
- Document assumptions explicitly
- Consider code contracts (requires/ensures)

## Example

```csharp
using System;

public sealed class Account
{
    // Invariant: balance >= 0.
    public decimal Balance { get; private set; }

    public Account(decimal openingBalance)
    {
        ArgumentOutOfRangeException.ThrowIfNegative(openingBalance);
        Balance = openingBalance;
    }

    // Precondition: amount is positive and available.
    // Postcondition: balance is reduced by that amount.
    public void Withdraw(decimal amount)
    {
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(amount);
        if (amount > Balance) throw new InvalidOperationException("Insufficient funds");
        Balance -= amount;
    }
}
```

## Related

- [poka-yoke](../knowledge/poka-yoke.md) - Make errors impossible
- [security-002-input-validation-first](../security/security-002-input-validation-first-88.md) - Validate at boundaries
- [design-008-semantic-precision](design-008-semantic-precision.md)
- [design-approaches-detailed](design-approaches-detailed.md)
- [design-composability](design-composability.md)
- [design-diagrams](design-diagrams.md)
- [design-entry-criteria](design-entry-criteria.md)
