# Advanced Calibration Notes

<!-- doc-accuracy: external-sdk Stripe -- examples call the Stripe SDK, not this repository -->

Supplement to the five quality sections in [Calibration Examples](calibration-examples.md).

## How assess.py scores coupling

`assess.py` scores coupling as `10 - scored imports`, floored at 1, at confidence 0.6.
Go standard-library imports appear in the report but are not scored.
A Go path is standard when its first element has no dot.
Packages of the module named in the nearest `go.mod` always count.
The cgo pseudo-package `"C"` also counts.
Ten imports such as `fmt`, `os`, and `time` therefore score 10, not 1.
Python standard-library statements and C# `System` namespace directives are not scored either.
Their breakdown line appears only when at least one is present.

---

## Language-Specific Adaptations

### Python: Duck Typing Encapsulation

```python
class Example:
    def __init__(self):
        self._private = "use single underscore"  # Convention
        self.__really_private = "double underscore mangles name"  # Rare
```

Score based on convention adherence, not enforcement.

### TypeScript: Interface Segregation

```typescript
import Stripe from "stripe";

// Good coupling (10/10)
interface PaymentProcessor {
  charge(amount: number): Promise<boolean>;
}

class OrderWithPaymentProcessor {
  constructor(private payment: PaymentProcessor) {}

  pay(totalCents: number): Promise<boolean> {
    return this.payment.charge(totalCents);
  }
}

// Poor coupling (4/10)
class OrderWithStripe {
  constructor(private payment: Stripe) {}  // Concrete dependency

  async pay(totalCents: number, paymentMethod: string, orderId: string): Promise<boolean> {
    const intent = await this.payment.paymentIntents.create(
      {
        amount: totalCents,
        currency: "usd",
        payment_method: paymentMethod,
        payment_method_types: ["card"],
        confirm: true,
      },
      { idempotencyKey: orderId },
    );
    return intent.status === "succeeded";
  }
}
```

### C#: Property Encapsulation

```csharp
// Perfect encapsulation (10/10)
public class BankAccount
{
    private decimal _balance;

    public decimal Balance => _balance;  // Read-only property

    public void Deposit(decimal amount) => _balance += amount;
}

// Weak encapsulation (4/10)
public class BankAccount
{
    public decimal Balance { get; set; }  // Public setter
}
```

---

## Calibration Workshop

Use these examples in team calibration sessions:

1. **Round 1**: Score examples independently
2. **Round 2**: Compare scores, discuss differences
3. **Round 3**: Reach consensus on borderline cases
4. **Round 4**: Create team-specific examples

**Goal**: 80%+ agreement on scores within ±1 point.
