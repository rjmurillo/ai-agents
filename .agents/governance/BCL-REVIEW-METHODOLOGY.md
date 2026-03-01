# BCL-Grade Code Review Methodology

> **Status**: Canonical Source of Truth
> **Last Updated**: 2026-02-21
> **RFC 2119**: This document uses RFC 2119 key words.

## Purpose

Methodology for conducting BCL-grade critical code reviews. Use this process when reviewing .NET code for production readiness, especially for components that may be candidates for BCL integration.

---

## Review Categories

### 1. Thread Safety Analysis

| Check | Evidence Required |
|-------|-------------------|
| Race conditions in atomic operations | Identify all shared mutable state |
| TOCTOU vulnerabilities | Check-then-act patterns flagged |
| Memory ordering with Volatile/Interlocked | Verify barrier semantics |
| Lock-free algorithm correctness | Prove linearizability |

**Questions to answer**:

- What happens if two threads call this method simultaneously?
- Is this read/write atomic?
- Can the disposal flag be missed between check and use?

### 2. Resource Management

| Check | Evidence Required |
|-------|-------------------|
| IDisposable implementation | Dispose pattern completeness |
| Circular reference detection | Object graph analysis |
| Memory leak prevention | Finalizer presence when required |
| Owned vs borrowed resources | Clear ownership semantics |

**Questions to answer**:

- Does this class own its dependencies?
- Can a circular reference prevent garbage collection?
- Is finalizer needed to break reference cycles?

### 3. Edge Cases and Boundaries

| Check | Evidence Required |
|-------|-------------------|
| Null handling in all paths | Guards at entry points |
| Integer overflow in counters | Interlocked usage |
| Exception propagation from dependencies | Try/catch appropriateness |
| Concurrent modification scenarios | Enumeration safety |

**Questions to answer**:

- What happens if every parameter is null?
- What happens after 4 billion increments?
- What happens if the inner dependency throws?

### 4. API Design Compliance

| Check | Evidence Required |
|-------|-------------------|
| Interface contract obligations | Documentation completeness |
| XML documentation coverage | All public members documented |
| Thread safety documentation | `<threadsafety>` tag present |
| Exception documentation | All throws documented |

### 5. Performance Analysis

| Check | Evidence Required |
|-------|-------------------|
| Hot-path allocations | Zero allocations verified |
| Interlocked vs lock choice | Lock-free where possible |
| Pre-allocation patterns | Array/collection sizing |

---

## Review Process

### Phase 1: Automated Analysis

Run these tools before manual review:

```bash
# 1. Static analysis
dotnet build --warnaserror

# 2. Thread safety analysis (if available)
# Tools: ThreadSanitizer, Rider thread safety inspection

# 3. Coverage report
dotnet test --collect:"XPlat Code Coverage"
```

### Phase 2: Parallel Agent Analysis

Launch parallel Explore agents for:

1. **Main Implementation Agent**
   - Review core logic
   - Identify thread safety concerns
   - Check resource management

2. **Test Coverage Agent**
   - Gap identification
   - Missing edge cases
   - Concurrent scenario coverage

3. **Supporting Code Agent**
   - Review helper classes
   - Check interface implementations
   - Validate extension methods

### Phase 3: Findings Generation

Generate findings with:

| Field | Description |
|-------|-------------|
| Severity | Critical, High, Medium, Low |
| Category | Thread Safety, Resources, Edge Cases, API, Performance |
| Location | `file:line` reference |
| Code Snippet | Problematic code excerpt |
| Issue | Specific problem description |
| Fix | Recommended resolution |

Example:

```markdown
**Severity**: Critical
**Category**: Thread Safety
**Location**: `MeteredMemoryCache.cs:145`

**Code**:
```csharp
if (!_disposed)
{
    _inner.Set(key, value);
}
```

**Issue**: TOCTOU race condition. Disposal check not atomic with operation.

**Fix**: Use Volatile.Read and handle ObjectDisposedException:
```csharp
ObjectDisposedException.ThrowIf(Volatile.Read(ref _disposed) != 0, this);
_inner.Set(key, value);
```
```

### Phase 4: Prioritization

Categorize findings:

| Priority | Definition | Timeline |
|----------|------------|----------|
| P0 (Blocking) | Data corruption, security vulnerability, crash | Must fix before merge |
| P1 (Should fix) | Correctness issue, significant performance | Before release |
| P2 (Nice to have) | Code quality, minor optimization | Backlog |

---

## Output Format

### Review Summary Template

```markdown
## BCL-Grade Review: [Component Name]

### Summary
- **Files Reviewed**: N
- **Lines of Code**: N
- **Test Coverage**: N%

### Findings by Severity

| Severity | Count |
|----------|-------|
| Critical | N |
| High | N |
| Medium | N |
| Low | N |

### P0 Issues (Blocking)

[List all P0 issues with full details]

### P1 Issues (Should Fix)

[List all P1 issues with full details]

### P2 Issues (Nice to Have)

[List all P2 issues with full details]

### Recommendations

[Summary of key improvements needed]
```

---

## Validation Hooks

### Pre-Merge Checklist

Before approving .NET code for merge:

- [ ] All P0 issues resolved
- [ ] Thread safety tests added for concurrent operations
- [ ] Disposal tests verify idempotency
- [ ] Edge case tests cover boundaries
- [ ] XML documentation complete
- [ ] No compiler warnings

### Post-Merge Validation

After merge, verify:

- [ ] CI passes on main branch
- [ ] Coverage thresholds maintained
- [ ] No new static analysis warnings

---

## Agent Integration

### Invoking BCL Review

To invoke a BCL-grade review:

```markdown
Review [Component] using BCL-grade methodology.
Focus on thread safety, resource management, and edge cases.
Generate findings with severity ratings.
```

### Agent Responsibilities

| Agent | Responsibility |
|-------|----------------|
| Implementer | Apply BCL standards during implementation |
| QA | Verify test coverage meets BCL requirements |
| Security | Review for thread safety vulnerabilities |
| Critic | Validate findings are properly categorized |

---

## References

- [DOTNET-BCL-STANDARDS.md](DOTNET-BCL-STANDARDS.md): Code standards
- [.NET Framework Design Guidelines](https://docs.microsoft.com/en-us/dotnet/standard/design-guidelines/)
- BCL Code Review Examples: dotnet/runtime repository
