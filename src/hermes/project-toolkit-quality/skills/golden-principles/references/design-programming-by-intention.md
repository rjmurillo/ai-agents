---
source: wiki/concepts/Design Principles/Programming by Intention.md
created: 2026-04-11
review-by: 2026-07-11
---

# Programming by Intention

<!-- doc-accuracy: external-sdk dotnet -- C# examples are illustrative .NET code, not this repository -->

Express intent over implementation. Write code that reads like a description of what it does, not how it does it.

## The Sergeant Pattern

A "sergeant" method directs workflow by calling well-named private methods. The top-level method expresses **what** happens. Private methods contain **how** it happens.

| Role | Responsibility | Visibility |
|------|----------------|------------|
| Sergeant | Directs workflow, calls privates | `public` |
| Privates | Implement specific operations | `private` |

## Good Example

```csharp
using System;
using System.Collections.Generic;
using System.Linq;

public sealed record Customer(string Email, bool IsPremium);

public sealed record OrderItem(string ProductId, int Quantity)
{
    public decimal Price { get; set; }
}

public sealed record Order(Customer Customer, IReadOnlyList<OrderItem> Items)
{
    public bool Confirmed { get; set; }
}

public sealed class OrderProcessor(
    IReadOnlyDictionary<string, decimal> prices,
    Action<IReadOnlyList<OrderItem>> reserve,
    Action<decimal> charge,
    Action<string> sendConfirmation)
{
    public void ProcessOrder(Order order)
    {
        ValidateOrder(order);
        ApplyPricing(order);
        ReserveInventory(order);
        ChargePayment(order);
        ConfirmOrder(order);
        NotifyCustomer(order);
    }

    private static void ValidateOrder(Order order)
    {
        if (order.Confirmed || order.Items.Count == 0 || order.Items.Any(item => item.Quantity <= 0))
            throw new InvalidOperationException("Order must be unconfirmed and contain positive quantities.");
    }

    private void ApplyPricing(Order order)
    {
        foreach (var item in order.Items)
            item.Price = prices[item.ProductId] * (order.Customer.IsPremium ? 0.9m : 1m);
    }

    private void ReserveInventory(Order order) => reserve(order.Items);

    private void ChargePayment(Order order) => charge(order.Items.Sum(item => item.Price * item.Quantity));

    private static void ConfirmOrder(Order order) => order.Confirmed = true;

    private void NotifyCustomer(Order order) => sendConfirmation(order.Customer.Email);
}
```

The caller supplies inventory, payment, and notification operations. This example focuses on workflow structure.

## Bad Example: Mixed Concerns

This version uses the same order types and inlines validation and pricing.

```csharp
using System;
using System.Collections.Generic;

public sealed class InlineOrderPricing(IReadOnlyDictionary<string, decimal> prices)
{
    public void ProcessOrder(Order order)
    {
        // Validation mixed with workflow
        if (order.Items.Count == 0)
            throw new InvalidOperationException("Order has no items");
        // Pricing logic mixed in
        foreach (var item in order.Items)
        {
            item.Price = prices[item.ProductId];
            if (order.Customer.IsPremium)
                item.Price *= 0.9m;
        }
    }
}
```

## Benefits

| Benefit | Explanation |
|---------|-------------|
| Method cohesion | Each method does one thing |
| Separation of concerns | Workflow separate from implementation |
| Clarity | Clear code is better than comments |
| Discoverability | Easy to find where specific logic lives |
| No extra work | Natural way to write code |
| Continued ROI | Code stays maintainable over time |

## Naming Conventions

| Intent | Name Examples |
|--------|--------------|
| Check a condition | `IsValid()`, `NeedsSorting()`, `HasPermission()` |
| Get data | `GetEmployees()`, `FetchOrders()` |
| Perform action | `ValidateOrder()`, `PrintHeader()`, `SendNotification()` |
| Transform | `FormatForDisplay()`, `ConvertToDto()` |

## Anti-Patterns

| Anti-Pattern | Problem |
|--------------|---------|
| Long methods | Mix workflow and implementation |
| Cryptic names | `DoStuff()`, `Process()`, `Handle()` |
| Comments explaining "what" | Code should explain itself |
| Deep nesting | Extract to named methods instead |
