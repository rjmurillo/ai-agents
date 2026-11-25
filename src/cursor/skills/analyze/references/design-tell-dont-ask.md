---
source: wiki/concepts/Design Principles/Tell Dont Ask.md
created: 2026-04-11
review-by: 2026-07-11
---

# Tell, Don't Ask

<!-- doc-accuracy: external-sdk dotnet -- C# examples use the .NET base class library, not this repository -->

> "Tell objects what to do, don't ask them for data and act on it yourself."

Attribution: Pragmatic Programmers, related to Law of Demeter.

## Core Insight

Instead of asking an object for data and making decisions based on that data, tell the object what you want done and let it figure out how.

## Ask vs Tell

```csharp
const decimal amount = 20m;

// ASK (procedural, avoid)
var exposedAccount = new ExposedAccount { Balance = 100m };
if (exposedAccount.Balance >= amount && amount > 0)
{
    exposedAccount.Balance -= amount;
}

// TELL (object-oriented, prefer)
var account = new Account(100m);
account.Withdraw(amount);

sealed class ExposedAccount
{
    public decimal Balance { get; set; }
}

sealed class Account(decimal openingBalance)
{
    public decimal Balance { get; private set; } = openingBalance;

    public bool Withdraw(decimal amount)
    {
        if (amount <= 0 || amount > Balance)
            return false;

        Balance -= amount;
        return true;
    }
}
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
using System.Collections.Generic;
using System.Linq;

static decimal AskForDiscount(Order order)
{
    // BAD: Feature envy
    if (order.Customer.IsPremium && order.Items.Count > 5)
        return order.Total * 0.1m;

    return 0m;
}

// GOOD: Tell the order
static decimal TellOrderToCalculateDiscount(Order order) => order.CalculateDiscount();

sealed record Customer(bool IsPremium);

sealed record Order(Customer Customer, IReadOnlyList<decimal> Items)
{
    public decimal Total => Items.Sum();

    public decimal CalculateDiscount() => Customer.IsPremium && Items.Count > 5 ? Total * 0.1m : 0m;
}
```

### Getter Chains (Law of Demeter violations)

```csharp
using System;

var customer = new Customer(new Address("Seattle"));

// BAD: Asking through a chain
var city = customer.Address.City;
Console.WriteLine(city);

// GOOD: Tell the customer what you need
if (customer.IsLocatedIn("Seattle"))
    Console.WriteLine("Customer qualifies for Seattle delivery.");

sealed record Address(string City);

sealed record Customer(Address Address)
{
    public bool IsLocatedIn(string city) => string.Equals(Address.City, city, StringComparison.OrdinalIgnoreCase);
}
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
