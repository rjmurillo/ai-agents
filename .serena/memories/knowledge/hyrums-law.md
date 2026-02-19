# Hyrum's Law

**Created**: 2026-01-10
**Category**: Mental Models / API Design

## The Law

"With a sufficient number of users of an API, it does not matter what you promise in the contract: all observable behaviors will be depended on by somebody."

**Attribution**: Named after Hyrum Wright (Google), popularized by Titus Winters.

## Core Insight

Every observable behavior becomes a de facto contract:

- Error message wording
- Response timing
- Item ordering in unordered collections
- Whitespace in output
- Exception types and messages

## Application to This Project

**When changing scripts or skills**:

1. Assume all output behaviors have dependents
2. Check for consumers parsing output (CI workflows, tests)
3. Consider what might break beyond explicit contract

**When reviewing PRs**:

1. Flag changes to observable behavior
2. Check if error messages are parsed elsewhere
3. Verify exit codes remain consistent

## Implications

- Testing cannot catch all implicit dependencies
- API evolution is harder than it appears
- Deprecation before removal is essential

## Mitigation Strategies

1. Be conservative in what you send
2. Use semantic versioning with breaking change discipline
3. Document implicit behaviors that might be relied upon
4. Use output schemas to make contracts explicit

## Related

- [foundational-knowledge-index](foundational-knowledge-index.md): Overview
- [chestertons-fence](chestertons-fence.md): Understand before changing
- `.agents/analysis/foundational-engineering-knowledge.md`: Full context
