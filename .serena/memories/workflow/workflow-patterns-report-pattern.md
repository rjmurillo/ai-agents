# Report Generation Pattern

**Statement**: Generate markdown reports with unique comment ID for idempotent updates

**Context**: AI review comments on PRs

**Evidence**: Comment ID enables `post_pr_comment()` to update existing comments

**Atomicity**: 88%

**Impact**: 8/10

## Template

```markdown
<!-- UNIQUE-COMMENT-ID -->
## Report Title

> [!NOTE|TIP|WARNING|CAUTION]
> **Verdict: STATUS**

<details>
<summary>Details</summary>
...
</details>

---
<sub>Powered by [Workflow Name](https://github.com/repo) workflow</sub>
```

## Why

- Comment ID enables idempotent updates via `post_pr_comment()`
- Prevents duplicate comments on re-runs
- `<details>` keeps long content collapsed
- Footer provides audit trail to workflow

## Related

- [workflow-authorization-testable-pattern](workflow-authorization-testable-pattern.md)
- [workflow-false-positive-verdict-parsing-2025-12-28](workflow-false-positive-verdict-parsing-2025-12-28.md)
- [workflow-false-positive-verdict-parsing-fix-2025-12-28](workflow-false-positive-verdict-parsing-fix-2025-12-28.md)
- [workflow-patterns-batch-changes-reduce-cogs](workflow-patterns-batch-changes-reduce-cogs.md)
- [workflow-patterns-composite-action](workflow-patterns-composite-action.md)
