# Workflow: Batch Changes to Reduce Bot COGS

**Date**: 2025-12-24
**Source**: User directive
**Validation Count**: 2 (Session 04 retrospective - confirmed helpful)

## Rule

Do NOT push feature branches immediately after committing. Batch up changes locally before pushing to minimize bot runs.

## Rationale

- Each push triggers AI reviewer bots (CodeRabbit, Copilot, AI PR Quality Gate)
- Bot runs have COGS (Cost of Goods Sold) - token/API costs
- Multiple small pushes = multiple expensive bot runs
- One batched push = one bot run for all changes

## Practice

1. Create feature branch locally
2. Make multiple commits as needed
3. Continue working until a logical batch is complete
4. Only push when ready for PR review
5. Prefer larger, complete PRs over incremental pushes

## When to Push

- Implementation is complete for the issue/feature
- All related changes are committed
- Ready for human review
- Explicitly asked to create PR

## Anti-pattern

```
# BAD: Push after every commit
git commit -m "add RCA"
git push  # triggers bots
git commit -m "add fix plan"  
git push  # triggers bots again
```

```
# GOOD: Batch commits, push once
git commit -m "add RCA"
git commit -m "add fix plan"
git commit -m "implement retry logic"
# ... continue working ...
git push  # one bot run for all changes
```

## Related

- [workflow-authorization-testable-pattern](workflow-authorization-testable-pattern.md)
- [workflow-composite-action](workflow-composite-action.md)
- [workflow-false-positive-verdict-parsing-2025-12-28](workflow-false-positive-verdict-parsing-2025-12-28.md)
- [workflow-false-positive-verdict-parsing-fix-2025-12-28](workflow-false-positive-verdict-parsing-fix-2025-12-28.md)
- [workflow-matrix-artifacts](workflow-matrix-artifacts.md)
