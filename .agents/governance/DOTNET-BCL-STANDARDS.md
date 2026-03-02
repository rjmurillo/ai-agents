# .NET BCL-Grade Code Standards

> **Status**: Canonical Source of Truth
> **Last Updated**: 2026-02-21
> **RFC 2119**: This document uses RFC 2119 key words.

## Purpose

Standards for writing production-quality .NET code suitable for Base Class Library (BCL) integration. Agents generating .NET code MUST follow these patterns.

**Target Audience**: AI agents implementing .NET code, human reviewers validating agent output.

---

## Thread Safety Requirements

### Atomic Operations for Counters

```csharp
// WRONG - race condition
_counter++;

// CORRECT - atomic increment
private long _counter;
Interlocked.Increment(ref _counter);
```

### Volatile Reads for State Checks

```csharp
// WRONG - may read stale value
if (_disposed) return;

// CORRECT - volatile read
private int _disposed;
if (Volatile.Read(ref _disposed) != 0) return;
```

### Idempotent Disposal

```csharp
// CORRECT - thread-safe, idempotent disposal
private int _disposed;

public void Dispose()
{
    if (Interlocked.Exchange(ref _disposed, 1) != 0)
        return;
    GC.SuppressFinalize(this);
    // cleanup...
}
```

### Thread Safety Documentation

```csharp
/// <summary>
/// Thread-safe cache with expiration support.
/// </summary>
/// <threadsafety>
/// This class is thread-safe for concurrent read and write operations.
/// Enumeration is thread-safe but may not reflect concurrent modifications.
/// </threadsafety>
public class ThreadSafeCache<TKey, TValue> : IDisposable
```

---

## Resource Management Requirements

### Finalizer for Circular References

When a class owns disposable resources that may form circular references, MUST add a finalizer:

```csharp
// CORRECT - finalizer breaks circular references
~MyClass()
{
    Dispose();
}

public void Dispose()
{
    if (Interlocked.Exchange(ref _disposed, 1) != 0)
        return;
    GC.SuppressFinalize(this);
    _ownedResource?.Dispose(); // Break reference cycle
    if (_disposeInner)
        _inner.Dispose();
}
```

### Disposal Order

1. Mark as disposed (atomic)
2. Suppress finalizer
3. Dispose owned resources (breaks cycles)
4. Dispose optional inner resources

---

## Exception Handling Requirements

### Exception Documentation

```csharp
/// <summary>
/// Gets the value associated with the specified key.
/// </summary>
/// <param name="key">The key to look up.</param>
/// <returns>The associated value.</returns>
/// <exception cref="ArgumentNullException">
/// Thrown when <paramref name="key"/> is <see langword="null"/>.
/// </exception>
/// <exception cref="KeyNotFoundException">
/// Thrown when <paramref name="key"/> is not found in the cache.
/// </exception>
/// <exception cref="ObjectDisposedException">
/// Thrown when this instance has been disposed.
/// </exception>
public TValue Get(TKey key)
```

### Guard Clauses at Method Start

```csharp
public void Add(string key, object value)
{
    // All guards first, in consistent order
    ArgumentNullException.ThrowIfNull(key);
    ArgumentNullException.ThrowIfNull(value);
    ObjectDisposedException.ThrowIf(Volatile.Read(ref _disposed) != 0, this);

    // Implementation follows guards
}
```

---

## Performance Requirements

### Zero Hot-Path Allocations

```csharp
// WRONG - allocates on every call
public IReadOnlyCollection<Tag> GetTags()
{
    return new List<Tag>(_tags);
}

// CORRECT - pre-allocated array
private readonly KeyValuePair<string, object?>[] _tags;

public ReadOnlySpan<KeyValuePair<string, object?>> Tags => _tags;
```

### Spans for Temporary Buffers

```csharp
// WRONG - heap allocation
byte[] buffer = new byte[256];

// CORRECT - stack allocation
Span<byte> buffer = stackalloc byte[256];
```

### Manual Loops in Hot Paths

```csharp
// WRONG - LINQ overhead in hot path
var result = items.Where(x => x.IsValid).Select(x => x.Value).ToList();

// CORRECT - manual loop
var result = new List<T>(items.Length);
for (int i = 0; i < items.Length; i++)
{
    if (items[i].IsValid)
        result.Add(items[i].Value);
}
```

---

## API Design Requirements

### Parameter Validation Order

1. Null checks
2. Range/bounds checks
3. Disposed checks
4. Business rule validation

### Consistent Naming

| Pattern | Naming Convention |
|---------|-------------------|
| Boolean properties | `IsDisposed`, `HasValue`, `CanExecute` |
| Event handlers | `On{Event}` |
| Factory methods | `Create{Type}` |
| Try-pattern methods | `TryGet{Value}` |

### Cancellation Token Support

```csharp
// CORRECT - cancellation as last parameter
public async Task<T> GetAsync(string key, CancellationToken cancellationToken = default)
{
    cancellationToken.ThrowIfCancellationRequested();
    // implementation
}
```

---

## Test Requirements

### Exact Value Assertions

```csharp
// WRONG - imprecise assertion
Assert.True(actualCount > 0);

// CORRECT - exact assertion
Assert.Equal(5, actualCount);
```

### Thread Safety Tests

```csharp
[Fact]
public async Task ConcurrentOperations_ShouldBeThreadSafe()
{
    var cache = new ThreadSafeCache<string, int>();

    await Parallel.ForEachAsync(
        Enumerable.Range(0, 1000),
        new ParallelOptions { MaxDegreeOfParallelism = 20 },
        async (i, ct) =>
        {
            cache.Add($"key{i}", i);
            _ = cache.TryGet($"key{i % 100}", out _);
            await Task.Yield();
        });

    Assert.True(cache.Count > 0);
}
```

### Disposal Race Condition Tests

```csharp
[Fact]
public void Dispose_DuringOperation_ShouldNotThrow()
{
    var cache = new ThreadSafeCache<string, int>();
    var tasks = new List<Task>();

    for (int i = 0; i < 100; i++)
    {
        tasks.Add(Task.Run(() => cache.Add(Guid.NewGuid().ToString(), 1)));
    }

    cache.Dispose();

    // Should not throw - disposed state is handled gracefully
    Assert.DoesNotThrow(() => Task.WaitAll(tasks.ToArray()));
}
```

### Edge Case Coverage

Required test scenarios:

- Null inputs on all public methods
- Empty collections
- Boundary values (0, -1, int.MaxValue, long.MaxValue)
- Concurrent modification
- Double disposal
- Disposed state access

---

## Documentation Requirements

### XML Documentation Coverage

All public APIs MUST have:

- `<summary>` describing purpose
- `<param>` for each parameter
- `<returns>` for non-void methods
- `<exception>` for each thrown exception
- `<threadsafety>` for thread-safe types
- `<example>` for complex APIs

### Remarks Section Usage

Use `<remarks>` for:

- Implementation notes
- Performance characteristics
- Usage guidelines
- Related types

---

## Quick Reference Checklist

Before submitting .NET code for review:

- [ ] All counters use Interlocked operations
- [ ] Disposed checks use Volatile.Read
- [ ] Disposal is idempotent (Interlocked.Exchange pattern)
- [ ] Finalizer added if owning circular reference resources
- [ ] All exceptions documented
- [ ] Guard clauses at method start
- [ ] No allocations in hot paths
- [ ] Thread safety tests included
- [ ] Edge case tests included
- [ ] Full XML documentation coverage

---

## References

- [.NET Framework Design Guidelines](https://docs.microsoft.com/en-us/dotnet/standard/design-guidelines/)
- [Threading Best Practices](https://docs.microsoft.com/en-us/dotnet/standard/threading/)
- BCL Source: https://github.com/dotnet/runtime
