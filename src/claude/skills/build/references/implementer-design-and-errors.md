# Design Qualities and Error Handling

<!-- doc-accuracy: external-sdk dotnet -- C# examples use the .NET base class library, not this repository -->

Loaded by the `implementer` agent when it designs or refactors code. The agent body keeps a working rule for each topic.

Bottom-up. Design emerges from qualities, not from pattern selection.

1. **Qualities**: Cohesion, Coupling, DRY, Encapsulation, Testability
2. **Principles**: Open-Closed, Encapsulate by Policy/Reveal by Need, Separation of Concerns, Separate Use from Creation
3. **Practices**: Coding Standards, State Always Private, Programming by Intention, CVA, Encapsulate Constructors
4. **Patterns**: Strategy, Bridge, Adapter, Facade, Proxy, Decorator, Chain of Responsibility, Singleton, Abstract Factory, Template Method, Flyweight (used intentionally, not reflexively)
5. **Wisdom**: GoF, Fowler, Coplien

## Level 1: Qualities (diagnostic layer)

**Testability**: Hard to test indicates poor encapsulation, tight coupling, Law of Demeter violation, weak cohesion, or procedural code. Always ask "how would I test this?"

**Cohesion**: Class has single responsibility. Method has single function. Use Programming by Intention:

```csharp
using System;
using System.Collections.Generic;
using System.Linq;

public sealed record LineItem(decimal UnitPrice, int Quantity);
public sealed record Order(string Id, IReadOnlyList<LineItem> Items);
public sealed record OrderReceipt(string OrderId, decimal Total);

public sealed class OrderProcessor(Action<OrderReceipt> saveOrder)
{
    public void ProcessOrder(Order order)
    {
        if (!IsValid(order))
            throw new ArgumentException("The order must contain valid line items.", nameof(order));

        var items = GetLineItems(order);
        var subtotal = CalculateTotals(items);
        var total = ApplyDiscounts(subtotal);
        SaveOrder(order.Id, total);
    }

    private static bool IsValid(Order order) => order.Items.Count > 0 &&
        order.Items.All(item => item.Quantity > 0 && item.UnitPrice >= 0m);

    private static IReadOnlyList<LineItem> GetLineItems(Order order) => order.Items;

    private static decimal CalculateTotals(IReadOnlyList<LineItem> items) =>
        items.Sum(item => item.UnitPrice * item.Quantity);

    private static decimal ApplyDiscounts(decimal subtotal) => subtotal >= 100m ? subtotal * 0.9m : subtotal;

    private void SaveOrder(string orderId, decimal total) => saveOrder(new OrderReceipt(orderId, total));
}
```

**Coupling**: Four types exist:

- Identity: coupled to fact another type exists
- Representation: coupled to interface (method signatures)
- Inheritance: subtypes coupled to superclass changes
- Subclass: coupled to specific subclass

Goal: intentional coupling (documented, necessary) vs accidental (unplanned side effects).

**DRY**: Single authoritative representation for every piece of knowledge. Includes relationships and construction, not just code.

**Encapsulation**: Encapsulate by policy, reveal by need. Hidden things cannot be coupled to. Easier to break encapsulation later than add it.

## Error Handling Principles

**Fail-fast**: Detect errors at boundaries, fail immediately with clear messages.

**No silent failures**: Every error path must either throw, log, or return explicit failure.

**Retry with backoff**: For transient failures only. Max 3 retries with exponential backoff.

The caller classifies retryable failures and supplies an operation that is safe to retry.

```csharp
using System;
using System.Threading;
using System.Threading.Tasks;

public sealed class TransientException(string message, Exception cause) : Exception(message, cause) { }

public sealed class MaxRetriesExceededException(Exception cause) : Exception("All attempts failed.", cause) { }

public static class Retry
{
    public static async Task<T> WithRetry<T>(
        Func<CancellationToken, Task<T>> operation,
        int maxRetries = 3,
        CancellationToken cancellationToken = default)
    {
        ArgumentOutOfRangeException.ThrowIfNegative(maxRetries);
        ArgumentOutOfRangeException.ThrowIfGreaterThan(maxRetries, 3);

        for (int attempt = 0; ; attempt++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            try
            {
                return await operation(cancellationToken);
            }
            catch (TransientException error)
            {
                if (attempt == maxRetries)
                    throw new MaxRetriesExceededException(error);

                await Task.Delay(TimeSpan.FromSeconds(1 << attempt), cancellationToken);
            }
        }
    }
}
```

```python
import asyncio
from collections.abc import Awaitable, Callable


class TransientError(Exception):
    """A failure the operation has classified as safe to retry."""


class MaxRetriesExceededError(Exception):
    """The operation exhausted all attempts."""


async def with_retry[T](operation: Callable[[], Awaitable[T]], max_retries: int = 3) -> T:
    if not 0 <= max_retries <= 3:
        raise ValueError("max_retries must be between 0 and 3")

    attempt = 0
    while True:
        try:
            return await operation()
        except TransientError as error:
            if attempt == max_retries:
                raise MaxRetriesExceededError("All attempts failed") from error
            await asyncio.sleep(2**attempt)
            attempt += 1
```

**Error categories**:

| Category | Action | Example |
|----------|--------|---------|
| Validation | Fail fast, no retry | Invalid input, missing required field |
| Transient | Retry with backoff | Network timeout, rate limit |
| Fatal | Log and propagate | Out of memory, config missing |
| Business | Return result type | Insufficient funds, item unavailable |
