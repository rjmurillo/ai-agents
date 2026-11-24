# .NET BCL-Grade Code Standards

<!-- doc-accuracy: external-sdk dotnet -- C# examples use the .NET base class library and xUnit, not this repository; ADR-124 tracks declaration proof -->

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
using System.Threading;

public sealed class RequestCounter
{
    private long _counter;

    // WRONG - race condition
    public long IncrementUnsafely() => ++_counter;

    // CORRECT - atomic increment
    public long Increment() => Interlocked.Increment(ref _counter);
}
```

### Volatile Reads for State Checks

```csharp
using System.Threading;

public sealed class ShutdownState
{
    private int _disposed;

    // WRONG - may read a stale value
    public bool IsDisposedUnsafely => _disposed != 0;

    // CORRECT - volatile read
    public bool IsDisposed => Volatile.Read(ref _disposed) != 0;

    public void MarkDisposed() => Volatile.Write(ref _disposed, 1);
}
```

### Idempotent Disposal

```csharp
using System;
using System.IO;
using System.Threading;

public sealed class ExportFile(string path) : IDisposable
{
    private Stream? _stream = File.OpenWrite(path);

    // Only the caller that gets the previous stream disposes it.
    public void Dispose()
    {
        Interlocked.Exchange(ref _stream, null)?.Dispose();
        GC.SuppressFinalize(this);
    }
}
```

### Thread Safety Documentation

```csharp
using System.Collections.Concurrent;

/// <summary>
/// Thread-safe cache for values stored by key.
/// </summary>
/// <threadsafety>
/// This class is thread-safe for concurrent read and write operations.
/// </threadsafety>
public sealed class ThreadSafeCache<TKey, TValue> where TKey : notnull
{
    private readonly ConcurrentDictionary<TKey, TValue> _values = new();

    public int Count => _values.Count;

    public void Add(TKey key, TValue value) => _values[key] = value;

    public bool TryGet(TKey key, out TValue? value) => _values.TryGetValue(key, out value);
}
```

---

## Resource Management Requirements

### Finalizer for Directly Owned Unmanaged Resources

The garbage collector handles cycles in managed objects. Prefer `SafeHandle` for unmanaged handles.
When a type owns unmanaged memory directly, its finalizer must release that memory.

```csharp
using System;
using System.Runtime.InteropServices;
using System.Threading;

public sealed class NativeBuffer : IDisposable
{
    private nint _address;

    public NativeBuffer(int length)
    {
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(length);
        _address = Marshal.AllocHGlobal(length);
    }

    ~NativeBuffer() => Release();

    public void Dispose()
    {
        Release();
        GC.SuppressFinalize(this);
    }

    private void Release()
    {
        nint address = Interlocked.Exchange(ref _address, 0);
        if (address != 0)
            Marshal.FreeHGlobal(address);
    }
}
```

### Disposal Order

1. Mark as disposed (atomic)
2. Release owned unmanaged resources
3. Dispose owned managed resources on explicit disposal
4. Suppress finalization after cleanup succeeds

---

## Exception Handling Requirements

### Exception Documentation

```csharp
using System;
using System.Collections.Generic;

public sealed class Lookup<TKey, TValue>(IReadOnlyDictionary<TKey, TValue> values) : IDisposable
    where TKey : notnull
{
    private bool _disposed;

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
    {
        ArgumentNullException.ThrowIfNull(key);
        ObjectDisposedException.ThrowIf(_disposed, this);
        return values.TryGetValue(key, out var value) ? value : throw new KeyNotFoundException();
    }

    public void Dispose() => _disposed = true;
}
```

### Guard Clauses at Method Start

```csharp
using System;
using System.Collections.Generic;

public sealed class Cache : IDisposable
{
    private readonly Dictionary<string, object> _values = new();
    private bool _disposed;

    public void Add(string key, object value)
    {
        ArgumentNullException.ThrowIfNull(key);
        ArgumentNullException.ThrowIfNull(value);
        ObjectDisposedException.ThrowIf(_disposed, this);
        _values.Add(key, value);
    }

    public void Dispose()
    {
        _disposed = true;
        _values.Clear();
    }
}
```

---

## Performance Requirements

### Zero Hot-Path Allocations

```csharp
using System;
using System.Collections.Generic;

public sealed record Tag(string Name, object? Value);

public sealed class TagSnapshot(IEnumerable<Tag> tags)
{
    private readonly Tag[] _tags = new List<Tag>(tags).ToArray();

    // WRONG - allocates on every call
    public IReadOnlyCollection<Tag> GetTags() => new List<Tag>(_tags);

    // CORRECT - view over the pre-allocated array
    public ReadOnlySpan<Tag> Tags => _tags;
}
```

### Spans for Temporary Buffers

```csharp
using System;
using System.Security.Cryptography;

// WRONG - heap allocation
static byte[] HashWithHeapBuffer(ReadOnlySpan<byte> input) => Hash(input, new byte[256]);

// CORRECT - stack allocation
static byte[] HashWithStackBuffer(ReadOnlySpan<byte> input)
{
    Span<byte> buffer = stackalloc byte[256];
    return Hash(input, buffer);
}

static byte[] Hash(ReadOnlySpan<byte> input, Span<byte> buffer)
{
    if (input.Length > buffer.Length)
        throw new ArgumentOutOfRangeException(nameof(input));

    input.CopyTo(buffer);
    return SHA256.HashData(buffer[..input.Length]);
}
```

### Manual Loops in Hot Paths

```csharp
using System.Collections.Generic;
using System.Linq;

// WRONG - LINQ overhead in hot path
static List<T> CollectWithLinq<T>(Item<T>[] items) =>
    items.Where(x => x.IsValid).Select(x => x.Value).ToList();

// CORRECT - manual loop
static List<T> CollectWithLoop<T>(Item<T>[] items)
{
    var result = new List<T>(items.Length);
    for (int i = 0; i < items.Length; i++)
    {
        if (items[i].IsValid)
            result.Add(items[i].Value);
    }

    return result;
}

record struct Item<T>(bool IsValid, T Value);
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
using System.IO;
using System.Threading;
using System.Threading.Tasks;

// CORRECT - cancellation as last parameter
public static class TextStore
{
    public static Task<string> GetAsync(string path, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return File.ReadAllTextAsync(path, cancellationToken);
    }
}
```

---

## Test Requirements

### Exact Value Assertions

```csharp
using System.Linq;
using Xunit;

public sealed class CountTests
{
    [Fact]
    public void CountsEveryItem()
    {
        int actualCount = Enumerable.Range(1, 5).Count();

        // WRONG - imprecise assertion
        Assert.True(actualCount > 0);

        // CORRECT - exact assertion
        Assert.Equal(5, actualCount);
    }
}
```

### Thread Safety Tests

Use the `ThreadSafeCache` defined above in the test project.

```csharp
using System.Linq;
using System.Threading.Tasks;
using Xunit;

public sealed class ConcurrentCacheTests
{
    [Fact]
    public async Task ConcurrentOperations_PreserveEveryValue()
    {
        var cache = new ThreadSafeCache<string, int>();

        await Parallel.ForEachAsync(
            Enumerable.Range(0, 1000),
            new ParallelOptions { MaxDegreeOfParallelism = 20 },
            (i, _) =>
            {
                cache.Add($"key{i}", i);
                Assert.True(cache.TryGet($"key{i}", out int actual));
                Assert.Equal(i, actual);
                return ValueTask.CompletedTask;
            });

        Assert.Equal(1000, cache.Count);
    }
}
```

### Disposal Race Condition Tests

```csharp
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Xunit;

public sealed class DisposalTests
{
    [Fact]
    public async Task Dispose_DuringOperation_StopsFurtherWrites()
    {
        using var cache = new DisposableCache();
        var start = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var writers = Enumerable.Range(0, 100).Select(async i =>
        {
            await start.Task;
            return cache.TryAdd(i);
        }).ToArray();
        var dispose = Task.Run(async () =>
        {
            await start.Task;
            cache.Dispose();
        });

        start.SetResult();
        await Task.WhenAll(writers.Append<Task>(dispose));
        Assert.False(cache.TryAdd(100));
    }

    private sealed class DisposableCache : IDisposable
    {
        private readonly object _gate = new();
        private HashSet<int>? _entries = new();

        public bool TryAdd(int value)
        {
            lock (_gate)
                return _entries?.Add(value) ?? false;
        }

        public void Dispose()
        {
            lock (_gate)
                _entries = null;
        }
    }
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
