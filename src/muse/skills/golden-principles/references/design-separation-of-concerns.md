---
source: wiki/concepts/Design Principles/Separation of Concerns.md
created: 2026-04-11
review-by: 2026-07-11
---

# Separation of Concerns

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
public void ProcessOrder(Order order)
{
    ValidateOrder(order);           // Validation concern
    CalculateTotals(order);         // Calculation concern
    ApplyDiscounts(order);          // Business rules concern
    PersistOrder(order);            // Data access concern
    NotifyCustomer(order);          // Communication concern
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
