---
source: /home/richard/Documents/Mobile/wiki/concepts/Design Principles/Programming by Intention.md
created: 2026-04-11
review-by: 2026-07-11
---

# Programming by Intention

Express intent over implementation. Write code that reads like a description of what it does, not how it does it.

## The Sergeant Pattern

A "sergeant" method directs workflow by calling well-named private methods. The top-level method expresses **what** happens. Private methods contain **how** it happens.

| Role | Responsibility | Visibility |
|------|----------------|------------|
| Sergeant | Directs workflow, calls privates | `public` |
| Privates | Implement specific operations | `private` |

## Good Example

```csharp
public void ProcessOrder(Order order)
{
    ValidateOrder(order);
    ApplyPricing(order);
    ReserveInventory(order);
    ChargePayment(order);
    ConfirmOrder(order);
    NotifyCustomer(order);
}
```

## Bad Example: Mixed Concerns

```csharp
public void ProcessOrder(Order order)
{
    // Validation mixed with workflow
    if (order.Items.Count == 0)
        throw new InvalidOperationException("Order has no items");
    // Pricing logic mixed in
    foreach (var item in order.Items)
    {
        item.Price = _priceService.GetPrice(item.ProductId);
        if (order.Customer.IsPremium)
            item.Price *= 0.9m;
    }
    // Implementation details everywhere
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
