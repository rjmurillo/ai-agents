# Coupling Types and Intentional Coupling

## Four Types of Coupling

### Identity Coupling
One type coupled to the fact another exists.

**Example**: Class A references Class B by name.
```csharp
public class OrderProcessor
{
    public void Process(Order order) { ... }  // Coupled to Order's existence
}
```

**Impact**: Minimal. Just needs to know type exists.

### Representation Coupling
One type coupled to the interface of another.

**Example**: Class A depends on Class B's public methods/properties.
```csharp
public class OrderProcessor
{
    public void Process(Order order)
    {
        order.Validate();      // Coupled to Validate() method
        order.CalculateTotal(); // Coupled to CalculateTotal() method
    }
}
```

**Impact**: Changes to B's interface break A.

### Inheritance Coupling
Subtypes coupled to superclass changes.

**Example**: Derived class breaks when base class changes.
```csharp
public class DiscountedOrder : Order
{
    // Coupled to Order's protected/public members
    // Changes to Order's internals affect DiscountedOrder
}
```

**Impact**: Most brittle. Violates open-closed principle.

### Subclass Coupling
Coupling to a specific subclass rather than abstraction.

**Example**: Code depends on concrete implementation.
```csharp
public class ShoppingCart
{
    public void Checkout(CreditCardPayment payment)  // Bad: coupled to subclass
    {
        payment.ProcessCreditCard();
    }
}

// Better:
public class ShoppingCart
{
    public void Checkout(IPayment payment)  // Good: coupled to abstraction
    {
        payment.Process();
    }
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
