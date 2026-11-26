---
source: wiki/concepts/Design Principles/Separation of Concerns.md
created: 2026-04-11
review-by: 2026-07-11
---

# Separation of Concerns

<!-- doc-accuracy: external-sdk dotnet -- C# examples use the .NET base class library, not this repository -->

Decompose a system into distinct sections, each addressing a separate concern. Attribution: Edsger W. Dijkstra, "On the role of scientific thought" (1974).

A **concern** is a set of information that affects the code. Each section should address one concern, be independent, and be modifiable without affecting unrelated sections.

## Why It Matters

| Benefit | Explanation |
|---------|-------------|
| Easier understanding | Focus on one thing at a time |
| Easier maintenance | Changes isolated to relevant sections |
| Easier testing | Test concerns independently |
| Easier reuse | Decoupled concerns can be extracted |

## Levels of Separation

### Method Level

Use Programming by Intention to separate workflow from implementation:

```csharp
using System;
using System.Collections.Generic;
using System.Linq;

public sealed record LineItem(decimal Price, int Quantity);
public sealed record Order(string Id, string CustomerEmail, IReadOnlyList<LineItem> Items);

public sealed class OrderWorkflow(Action<string, decimal> persist, Action<string, string> notify)
{
    public void ProcessOrder(Order order)
    {
        ValidateOrder(order);                    // Validation concern
        decimal subtotal = CalculateTotals(order); // Calculation concern
        decimal total = ApplyDiscounts(subtotal);  // Business rules concern
        PersistOrder(order.Id, total);             // Data access concern
        NotifyCustomer(order);                     // Communication concern
    }

    private static void ValidateOrder(Order order)
    {
        if (order.Items.Count == 0 || order.Items.Any(item => item.Quantity <= 0 || item.Price < 0m))
            throw new ArgumentException("Order must contain valid line items.", nameof(order));
    }

    private static decimal CalculateTotals(Order order) => order.Items.Sum(item => item.Price * item.Quantity);

    private static decimal ApplyDiscounts(decimal subtotal) => subtotal >= 100m ? subtotal * 0.9m : subtotal;

    private void PersistOrder(string orderId, decimal total) => persist(orderId, total);

    private void NotifyCustomer(Order order) => notify(order.CustomerEmail, $"Order {order.Id} confirmed.");
}
```

### Class Level

Each class has a single responsibility (SRP):

| Class | Concern |
|-------|---------|
| `OrderValidator` | Validation rules |
| `PricingEngine` | Price calculation |
| `OrderRepository` | Data persistence |
| `NotificationService` | Customer communication |

### Layer Level

Separate architectural layers: Presentation, Business Logic, Data Access.

### Service Level

In distributed systems, separate by business capability (Order Service, Inventory Service, Payment Service, Notification Service).

## Common Violations

| Violation | Example |
|-----------|---------|
| Mixed concerns | Business logic in UI controllers |
| God classes | One class doing everything |
| Cross-cutting leakage | Logging logic scattered everywhere |
| Layer piercing | UI directly accessing database |

## Cross-Cutting Concerns

Some concerns span multiple layers: logging, security/authentication, caching, error handling, transactions.

Solution: use aspects, middleware, or decorators to apply cross-cutting concerns without polluting business code.
