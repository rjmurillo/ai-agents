# Design by Contract

**Category**: Software Design
**Source**: `.agents/analysis/senior-engineering-knowledge.md`
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
// Precondition: amount > 0
// Postcondition: balance reduced by amount
// Invariant: balance >= 0
public void Withdraw(decimal amount)
{
    if (amount <= 0) throw new ArgumentException("Amount must be positive");
    if (amount > Balance) throw new InvalidOperationException("Insufficient funds");
    Balance -= amount;
}
```

## Related

- `poka-yoke` - Make errors impossible
- `security-002-input-validation-first` - Validate at boundaries
