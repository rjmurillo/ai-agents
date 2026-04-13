# Performance Principles (Detailed)

## Pool and Reuse Pattern

### Core Concept
Borrow memory once, reuse, return. Minimize allocations in hot paths.

### Implementation
```csharp
// Use ArrayPool<T> for temporary buffers
var pool = ArrayPool<T>.Shared;
var buffer = pool.Rent(minimumSize);
try
{
    // Use buffer
}
finally
{
    pool.Return(buffer, clearArray: true);
}
```

### Key Rules
- **Copy data once** into pooled storage
- **Operate in place**: sort, slice, scan without creating new collections
- **Avoid creating objects/collections inside hot loops**
- **Groups are views** of memory, not new lists (use Span<T>, Memory<T>)

## ARM64/Cobalt Tuning Specifics

### Critical Configuration
```bash
export ThreadPool_UnfairSemaphoreSpinLimit=0
```

**Why**: ARM processors handle lock contention differently than x64. Default spin limits cause performance degradation on ARM64.

### Required Settings
- **Server GC enabled**: Better for multi-core ARM processors
- **Monitor GC metrics**:
  - gen0/gen1/gen2 collection counts
  - % time in GC (target <5%)
  - LOH (Large Object Heap) size
  - Peak working set

### Performance Targets
- **Cobalt achieves x64 parity** with proper config
- **Without tuning**: 30-50% slower than x64
- **With tuning**: Within 5% of x64 performance

### Verification Commands
```bash
dotnet-gcdump ps
dotnet-gcdump collect -p <PID>
dotnet-gcdump report <dump-file>
```

## Hot Path Optimization Checklist

1. **Measure first** (never optimize without profiling)
2. **Eliminate allocations** (use pooling, stack allocation, value types)
3. **Reduce virtual calls** (sealed classes, structs, static dispatch)
4. **Batch operations** (reduce loop overhead, vectorize when possible)
5. **Cache frequently accessed data** (but beware memory pressure)

## Common Anti-Patterns

| Anti-Pattern | Fix |
|--------------|-----|
| `ToList()` in LINQ chains | Use `AsEnumerable()` or iterate directly |
| String concatenation in loops | Use `StringBuilder` or `string.Create()` |
| Boxing value types | Use generic constraints or avoid object |
| Creating Task per item | Use `Parallel.ForEach` or batch processing |
| Regex in hot path | Compile regex, or use source generators (.NET 7+) |

## When to Apply
- Identified hot paths via profiling
- Performance-critical code paths (>1000 calls/sec)
- Large data processing (>10K items)
- Real-time systems with latency requirements

## Source
User preference: Richard Murillo's global CLAUDE.md (removed during token optimization 2026-01-04)

## Context
Richard led MDE .NET 8/ARM64/Cobalt modernization. These patterns achieved x64 parity on ARM64 Cobalt instances.
