---
source: wiki/concepts/Build/SDK-Style Projects.md, wiki/concepts/Design Principles/dotNET Monorepo Standards.md
created: 2026-04-11
review-by: 2026-07-11
note: Zero-Allocation Coroutines wiki page not found. Content focuses on allocation-free patterns from available sources. Expand when coroutines content is located.
---

# .NET Performance Patterns for Quality Assessment

<!-- doc-accuracy: external-sdk dotnet -- C# examples use the .NET base class library, not this repository -->

Allocation-free and performance-conscious patterns relevant to code quality scoring. These patterns affect testability, coupling, and encapsulation scores.

## Allocation-Free Patterns

### Span and Memory

Use `Span<T>` and `ReadOnlySpan<T>` for stack-based, zero-allocation slicing.

```csharp
using System;

// Allocation-free string parsing
static bool TryParseHeader(ReadOnlySpan<char> line, out ReadOnlySpan<char> key, out ReadOnlySpan<char> value)
{
    int separator = line.IndexOf(':');
    if (separator < 0)
    {
        key = default;
        value = default;
        return false;
    }

    key = line[..separator].Trim();
    value = line[(separator + 1)..].Trim();
    return true;
}
```

**Quality impact**: Testability 10/10 (pure function, no side effects). Coupling 10/10 (no dependencies).

### ArrayPool for Buffer Reuse

```csharp
using System;
using System.Buffers;
using System.IO;

delegate void ProcessBytes(ReadOnlySpan<byte> data);

static class StreamReaderExample
{
    public static void ReadChunk(Stream stream, ProcessBytes processData)
    {
        const int chunkSize = 4096;
        byte[] buffer = ArrayPool<byte>.Shared.Rent(chunkSize);
        try
        {
            int bytesRead = stream.Read(buffer, 0, chunkSize);
            if (bytesRead > 0)
                processData(buffer.AsSpan(0, bytesRead));
        }
        finally
        {
            ArrayPool<byte>.Shared.Return(buffer);
        }
    }
}
```

**Quality impact**: Encapsulation 8/10 (pool is shared global state, but usage is local). Non-redundancy 9/10 (eliminates repeated `new byte[]` allocations).

### ValueTask for Hot Paths

```csharp
using System;
using System.Collections.Generic;
using System.Threading.Tasks;

// Avoid Task allocation when result is often synchronous
static ValueTask<int> GetCachedValueAsync(
    string key,
    IReadOnlyDictionary<string, int> cache,
    Func<string, Task<int>> getFromStoreAsync)
{
    if (cache.TryGetValue(key, out int value))
    {
        return new ValueTask<int>(value); // No allocation
    }

    return new ValueTask<int>(getFromStoreAsync(key));
}
```

**Quality impact**: Coupling 9/10 (depends on abstraction via cache interface). Testability 9/10 (injectable cache).

## Patterns That Reduce Quality Scores

### Allocation in Hot Loops (Non-Redundancy: 3/10)

```csharp
using System;
using System.Collections.Generic;

// Bad: allocates on every iteration
static void ProcessWithAllocation(IEnumerable<int> items, Action<IReadOnlyList<string>> process)
{
    foreach (var item in items)
    {
        var result = new List<string>();  // Allocation per iteration
        result.Add(item.ToString());     // Another allocation
        process(result);
    }
}

// Better: reuse outside loop
// The callback must finish reading each batch before the list is reused.
static void ProcessWithReuse(IEnumerable<int> items, Action<IReadOnlyList<string>> process)
{
    var result = new List<string>();
    foreach (var item in items)
    {
        result.Clear();
        result.Add(item.ToString());
        process(result);
    }
}
```

### Boxing Value Types (Encapsulation: 4/10)

```csharp
using System;

// Bad: boxes int to object
object boxed = 42;
int unboxed = (int)boxed;

// Better: use generics
static T ReadValue<T>(T value) where T : struct => value;
Console.WriteLine(ReadValue(42));
```

### String Concatenation in Loops (Non-Redundancy: 2/10)

```csharp
using System.Collections.Generic;
using System.Text;

// Bad: O(n^2) allocations
static string Concatenate(IEnumerable<int> items)
{
    string result = "";
    foreach (var item in items)
        result += item.ToString();  // New string each iteration
    return result;
}

// Better: append to a growable buffer and create the final string once.
static string AppendItems(IEnumerable<int> items)
{
    var builder = new StringBuilder();
    foreach (var item in items)
        builder.Append(item);
    return builder.ToString();
}
```

## SDK-Style Project Detection

Modern .NET projects use SDK-style format. Legacy projects with verbose XML indicate migration debt.

**SDK-style indicator**: `Sdk` attribute on `<Project>` element.

**Legacy indicator**: `ToolsVersion` attribute, `ProjectGuid`, explicit MSBuild imports.

**Quality relevance**: Legacy project format increases coupling (explicit dependency declarations) and reduces testability (harder to multi-target, harder to run in CI).

## Quality Scoring Guidance

| Pattern | Cohesion | Coupling | Encapsulation | Testability | Non-Redundancy |
|---------|----------|----------|---------------|-------------|----------------|
| Span-based parsing | 10 | 10 | 9 | 10 | 9 |
| ArrayPool reuse | 8 | 8 | 8 | 8 | 9 |
| ValueTask caching | 9 | 9 | 8 | 9 | 8 |
| Allocation in loops | 6 | 7 | 5 | 7 | 3 |
| String concat loops | 5 | 7 | 5 | 7 | 2 |
| Boxing value types | 6 | 6 | 4 | 7 | 5 |

Use these scores as calibration anchors when assessing .NET code that handles high-throughput or memory-sensitive workloads.
