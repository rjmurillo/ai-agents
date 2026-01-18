# Implementation Fast Iteration

## Skill-Implementation-007: Small Commits for Fast CI Cycles (92%)

**Statement**: Small commits with focused changes reduce CI cycle time below 10 minutes

**Context**: When iterating on CI workflows or code requiring automated review (Copilot, multi-agent review). Faster feedback enables rapid refinement.

**Evidence**: PR #343: 5 iterations in 20 minutes (4min/cycle average) enabled comprehensive edge case handling

**Pattern**:

```text
Large Commit (slow):
- 20 files changed
- Mixed topics (feature + fix + refactor)
- 15+ minute CI run
- Complex review feedback
- Long debugging cycle

Small Commit (fast):
- 1-3 files changed
- Single logical change
- <10 minute CI run
- Focused review feedback
- Rapid iteration
```

**Metrics from PR #343**:

| Iteration | Files Changed | CI Time | Feedback | Fix Time |
|-----------|---------------|---------|----------|----------|
| 1 | 1 | 8 min | Zero SHA handling | 5 min |
| 2 | 1 | 7 min | Missing commit check | 4 min |
| 3 | 1 | 6 min | Dot notation | 3 min |
| 4 | 1 | 8 min | Exit code validation | 3 min |
| 5 | 1 | 7 min | All PASS | 0 min |

**Average cycle**: 4 minutes (commit → CI → review → fix)

**Benefits**:

1. **Faster feedback**: CI completes quickly, review comments arrive sooner
2. **Easier debugging**: Small change = clear cause for any failures
3. **Focused review**: Reviewers concentrate on single logical change
4. **Rapid refinement**: Quick iterations enable edge case discovery
5. **Lower frustration**: Short wait times maintain flow state

**When to Use**:

- Iterating on CI workflows with automated reviews
- Fixing bugs discovered through testing
- Responding to PR review comments
- Developing features with tight feedback loops

**When NOT to Use**:

- Batch of independent fixes (group related changes)
- Documentation-only changes (can bundle)
- Renaming/refactoring (atomic change may touch many files)

**Trade-offs**:

| Aspect | Small Commits | Large Commits |
|--------|---------------|---------------|
| CI time per commit | Short (<10min) | Long (>15min) |
| Total commits | More (5-10) | Fewer (1-2) |
| Review focus | High (single topic) | Low (multiple topics) |
| Git history | Granular | Compact |
| Iteration speed | Fast | Slow |

**Related Skills**:

- [agent-workflow-atomic-commits](agent-workflow-atomic-commits.md) - Commit atomicity principles
- [implementation-additive-approach](implementation-additive-approach.md) - Additive vs refactor timing
- [ci-quality-gates](ci-quality-gates.md) - Automated review integration

**Success Example**: PR #343 used fast iteration to discover and fix 4 edge cases that weren't obvious upfront:

1. Zero SHA (first commit on branch)
2. Missing commit (force-push)
3. Dot notation (.. vs ... for push events)
4. Exit code validation (silent failures)

Each discovered through Copilot review, fixed in <5 minutes, validated in next cycle.

---

## Related Files

- [agent-workflow-atomic-commits](agent-workflow-atomic-commits.md) - Atomic commit principles
- [ci-quality-gates](ci-quality-gates.md) - Automated review workflows
- [implementation-test-discovery](implementation-test-discovery.md) - Test-first patterns

## Related

- [implementation-001-memory-first-pattern](implementation-001-memory-first-pattern.md)
- [implementation-001-pre-implementation-test-discovery](implementation-001-pre-implementation-test-discovery.md)
- [implementation-002-test-driven-implementation](implementation-002-test-driven-implementation.md)
- [implementation-006-graphql-first](implementation-006-graphql-first.md)
- [implementation-additive-approach](implementation-additive-approach.md)
