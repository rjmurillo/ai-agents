# Coupling Types and Intentional Coupling

<!-- doc-accuracy: external-sdk dotnet -- C# examples use the .NET base class library, not this repository -->

## Four Types of Coupling

### Identity Coupling
One type coupled to the fact another exists.

**Example**: Class A references Class B by name.
```csharp
using System;

public sealed record Order(string Id);

public class OrderProcessor
{
    // This service forwards the order without reading its fields.
    public void Process(Order order, Action<Order> submit) => submit(order);
}
```

**Impact**: Minimal. Just needs to know type exists.

### Representation Coupling
One type coupled to the interface of another.

**Example**: Class A depends on Class B's public methods/properties.
```csharp
using System;

public sealed record Order(decimal UnitPrice, int Quantity)
{
    public void Validate()
    {
        if (UnitPrice < 0m || Quantity <= 0)
            throw new ArgumentException("An order needs a positive quantity and a nonnegative price.");
    }

    public decimal CalculateTotal() => UnitPrice * Quantity;
}

public class OrderProcessor
{
    public decimal Process(Order order)
    {
        order.Validate();      // Coupled to Validate() method
        return order.CalculateTotal(); // Coupled to CalculateTotal() method
    }
}
```

**Impact**: Changes to B's interface break A.

### Inheritance Coupling
Subtypes coupled to superclass changes.

**Example**: Derived class breaks when base class changes.
```csharp
public class Order(decimal unitPrice, int quantity)
{
    protected decimal UnitPrice { get; } = unitPrice;
    protected int Quantity { get; } = quantity;

    public virtual decimal CalculateTotal() => UnitPrice * Quantity;
}

public sealed class DiscountedOrder(decimal unitPrice, int quantity) : Order(unitPrice, quantity)
{
    // Depends on the inherited pricing fields and their units.
    public override decimal CalculateTotal() => UnitPrice * Quantity * 0.9m;
}
```

**Impact**: Most brittle. Violates open-closed principle.

### Subclass Coupling
Coupling to a specific subclass rather than abstraction.

**Example**: Code depends on concrete implementation.
```csharp
using System;

public interface IPayment
{
    string Process(decimal amount);
}

public sealed class CreditCardPayment(string cardToken, Func<string, decimal, string> chargeCard) : IPayment
{
    public string ProcessCreditCard(decimal amount)
    {
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(amount);
        return chargeCard(cardToken, amount);
    }

    public string Process(decimal amount) => ProcessCreditCard(amount);
}

public class CardOnlyShoppingCart
{
    // Coupled to a concrete card processor.
    public string Checkout(CreditCardPayment payment, decimal total) => payment.ProcessCreditCard(total);
}

// Better:
public class ShoppingCart
{
    public string Checkout(IPayment payment, decimal total) => payment.Process(total);
}
```

**Impact**: Violates dependency inversion, prevents substitution.

## Goal: Intentional Coupling, Not Accidental

### Intentional Coupling
- **Deliberate design decision**
- **Documented rationale**
- **Known trade-offs**
- **Appropriate for context**

### Accidental Coupling
- **Unintended side effect**
- **No design consideration**
- **Hidden dependencies**
- **Future maintenance burden**

## Coupling Reduction Strategies

| Problem | Solution |
|---------|----------|
| Identity coupling | Acceptable if unavoidable |
| Representation coupling | Use interfaces, design to contracts |
| Inheritance coupling | Favor delegation over inheritance (GoF) |
| Subclass coupling | Depend on abstractions (Dependency Inversion) |

## Decision Framework

When introducing coupling, ask:

1. **Is this coupling necessary?** (Try to delete it first)
2. **What type of coupling is it?** (Identity < Representation < Inheritance/Subclass)
3. **What are the trade-offs?** (Document in ADR if significant)
4. **Can we use a weaker form?** (Interface vs concrete, composition vs inheritance)

## Source
User preference: Richard Murillo's global CLAUDE.md (removed during token optimization 2026-01-04)

## Related Concepts
- GoF: Favor delegation over inheritance
- SOLID: Dependency Inversion Principle
- Software Hierarchy of Needs: Coupling quality attribute
