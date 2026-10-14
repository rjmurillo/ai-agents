---
source: wiki/concepts/Design Principles/Tell Dont Ask.md
created: 2026-04-11
review-by: 2026-07-11
---

# Tell, Don't Ask

> "Tell objects what to do, don't ask them for data and act on it yourself."

Attribution: Pragmatic Programmers, related to Law of Demeter.

## Core Insight

Instead of asking an object for data and making decisions based on that data, tell the object what you want done and let it figure out how.

## Ask vs Tell

```csharp
// ASK (procedural, avoid)
if (account.Balance >= amount)
{
    account.Balance -= amount;
}

// TELL (object-oriented, prefer)
account.Withdraw(amount);
```

## Why It Matters

| Benefit | Explanation |
|---------|-------------|
| Better encapsulation | Logic stays with data |
| Reduced coupling | Caller doesn't know internal structure |
| Single responsibility | Object manages its own state |
| Easier changes | Logic changes in one place |

## Common Violations to Detect

### Feature Envy

Code more interested in another object's data than its own:

```csharp
// BAD: Feature envy
if (order.Customer.IsPremium && order.Items.Count > 5)
    return order.Total * 0.1m;

// GOOD: Tell the order
return order.CalculateDiscount();
```

### Getter Chains (Law of Demeter violations)

```csharp
// BAD: Asking through a chain
var city = customer.Address.City;

// GOOD: Tell the customer what you need
if (customer.IsLocatedIn("Seattle")) { ... }
```

## Detection Checklist for Analysis

| Pattern | Ask (Flag It) | Tell (Accept It) |
|---------|---------------|-------------------|
| Validation | `if (order.IsValid()) Process(order)` | `order.ProcessIfValid()` |
| State change | `order.Status = OrderStatus.Shipped` | `order.Ship()` |
| Calculation | `items.Sum(i => i.Price)` | `cart.CalculateTotal()` |
| Formatting | `$"{c.FirstName} {c.LastName}"` | `c.GetDisplayName()` |

## When the Rule Does Not Apply

- Data Transfer Objects (DTOs): pure data containers
- Value Objects: immutable data with no behavior
- Reporting/Display: sometimes you need raw data for presentation
- Cross-cutting concerns: logging, auditing may inspect state

## Related Principles

- **Law of Demeter**: Only talk to immediate friends
- **SRP**: Object responsible for its behavior
- **Encapsulation**: Hide data, expose behavior
