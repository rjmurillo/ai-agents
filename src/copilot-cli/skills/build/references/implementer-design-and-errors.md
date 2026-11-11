# Design Qualities and Error Handling

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
// C#
public void ProcessOrder(Order order)
{
    if (!IsValid(order)) throw new ArgumentException(...);
    var items = GetLineItems(order);
    CalculateTotals(items);
    ApplyDiscounts(items);
    SaveOrder(order);
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

```csharp
// C#
public async Task<T> WithRetry<T>(Func<Task<T>> operation, int maxRetries = 3)
{
    for (int i = 0; i < maxRetries; i++)
    {
        try { return await operation(); }
        catch (TransientException) when (i < maxRetries - 1)
        {
            await Task.Delay(TimeSpan.FromSeconds(Math.Pow(2, i)));
        }
    }
    throw new MaxRetriesExceededException();
}
```

```python
# Python
async def with_retry(operation: Callable, max_retries: int = 3) -> Any:
    for i in range(max_retries):
        try:
            return await operation()
        except TransientError:
            if i < max_retries - 1:
                await asyncio.sleep(2**i)
    raise MaxRetriesExceededError()
```

**Error categories**:

| Category | Action | Example |
|----------|--------|---------|
| Validation | Fail fast, no retry | Invalid input, missing required field |
| Transient | Retry with backoff | Network timeout, rate limit |
| Fatal | Log and propagate | Out of memory, config missing |
| Business | Return result type | Insufficient funds, item unavailable |
