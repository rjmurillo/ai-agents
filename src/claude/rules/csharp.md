---
paths:
  - "**/*.cs"
  - "**/*.csproj"
  - "**/Directory.Build.*"
  - "**/*.cshtml"
  - "**/*.razor"
description: C# and .NET idioms, performance, and conventions. Applies when editing C#, project, or Razor files.
---

# C# and .NET Rules

These rules apply when you write or review C#. Baseline is C# 13 on .NET 9 (the
target for new work). Where a newer feature helps, name the version so the
reader can check their SDK. Defer to the repo's `.editorconfig`, `Directory.Build.*`,
and any analyzer config over personal preference.

## Language Level

- Prefer modern syntax that reduces noise: collection expressions (`[1, 2, 3]`),
  primary constructors, `required` members, target-typed `new`, pattern matching,
  and `switch` expressions. They state intent with less ceremony.
- Use `record` for immutable value-like data; `record struct` when the value is
  small and copied often. Use `class` when identity or mutability is the point.
- Make reference types non-nullable by default. Keep `<Nullable>enable</Nullable>`
  on and treat nullable warnings as errors. A `?` is a contract, not decoration.
- Use `file`-scoped namespaces and `global using` for the handful of namespaces
  every file needs. Do not hide domain types behind global usings.

## Allocation and Performance

- Operate on `Span<T>` / `ReadOnlySpan<T>` and `Memory<T>` for slicing without
  copying. Rent large transient buffers from `ArrayPool<T>.Shared` and return
  them in a `finally`.
- Avoid allocations on hot paths: no LINQ in tight loops, no `params` arrays per
  call, no closures captured in inner loops. Measure with BenchmarkDotNet before
  and after; do not optimize on a hunch.
- Prefer `struct` for small, short-lived values to keep them off the heap, but
  pass large structs by `in` to avoid defensive copies. A struct over ~16 bytes
  passed by value is usually a mistake.
- Use `StringBuilder` or `string.Create` for multi-step string building;
  interpolation is fine for one-shot formatting.

## Async

- Every awaitable that crosses an I/O or process boundary takes a
  `CancellationToken` and honors it. A method that ignores its token is a bug.
- Return `ValueTask` only for hot paths that frequently complete synchronously;
  default to `Task`. Never await a `ValueTask` twice.
- In libraries, use `ConfigureAwait(false)` on every await. In app or test code
  with a synchronization context you control, you may omit it.
- Never block on async with `.Result` or `.Wait()`; that deadlocks under a
  synchronization context and wastes a thread otherwise. Make the caller async.

## Style and Structure

- Methods do one thing, stay under 60 lines, and keep cyclomatic complexity at or
  below 10. Extract a private method before a comment that explains a block.
- Guard clauses first; keep the happy path on the leftmost indent. Use
  `ArgumentNullException.ThrowIfNull` and `ArgumentException.ThrowIfNullOrEmpty`.
- Names: PascalCase for types and members, camelCase for locals and parameters,
  `_camelCase` for private fields. Interfaces start with `I`. Async methods end
  with `Async`.
- Dispose owned resources with `using` declarations. Implement `IAsyncDisposable`
  when cleanup is itself async. Do not implement a finalizer unless you own an
  unmanaged handle.

## Tooling

- SDK-style projects, `global.json` to pin the SDK, and Central Package
  Management (`Directory.Packages.props`) so versions live in one place.
- xUnit or NUnit for tests, with `Moq` or `NSubstitute` at boundaries only; do not
  mock the type under test. Name tests `Method_State_ExpectedOutcome`.
- Treat analyzer and StyleCop warnings as errors in CI. Fix the cause, do not
  suppress with `#pragma` unless you justify it in a comment.

## Anti-Patterns to Reject

- **`async void`** outside an event handler. The caller cannot await it and an
  exception crashes the process. Return `Task`.
- **Swallowing exceptions** with `catch (Exception) { }` or `catch { }`. Catch the
  specific type you can handle; rethrow with `throw;` (not `throw ex;`, which
  resets the stack trace).
- **`.Result` / `.Wait()` / `.GetAwaiter().GetResult()`** on a Task to bridge sync
  and async. Deadlock risk and thread waste. Propagate async to the caller.
- **Mutable `public` fields** and `public` setters on invariant-bearing types.
  Encapsulate state; expose behavior, not data.
- **`DateTime.Now`** in domain logic. Inject a clock abstraction; use
  `DateTimeOffset.UtcNow` at the edge. Untestable time is a hidden dependency.

## References

- C# language reference: <https://learn.microsoft.com/dotnet/csharp/>
- .NET runtime performance guidance: <https://learn.microsoft.com/dotnet/core/extensions/>
- Framework design guidelines: <https://learn.microsoft.com/dotnet/standard/design-guidelines/>
- Async guidance (`ConfigureAwait`): <https://learn.microsoft.com/dotnet/csharp/asynchronous-programming/>
