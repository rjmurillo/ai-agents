# Running GitHub Workflows from a Branch

## Problem

When testing workflow changes, I often incorrectly assume:
- "The workflow runs on main, so I need to merge first"
- "I can't test workflow changes until they're in main"

This is WRONG. GitHub Actions can run workflows from any branch.

## Solution

Use `gh workflow run` with the `--ref` flag:

```bash
gh workflow run <workflow-name> --ref <branch-name>
```

## Examples

```bash
# Run pr-maintenance workflow from a feature branch
gh workflow run pr-maintenance.yml --ref fix/400-pr-maintenance-visibility

# Run with inputs
gh workflow run pr-maintenance.yml --ref feat/my-feature -f max_prs=10

# Run any workflow from any branch
gh workflow run ci.yml --ref experiment/new-feature
```

## Evidence

This was successfully used on 2025-12-27:
- Workflow: `pr-maintenance.yml`
- Branch: `fix/400-pr-maintenance-visibility`
- Result: Workflow ran successfully from the feature branch

## When to Use

- Testing workflow changes BEFORE merging to main
- Validating fixes on feature branches
- Running scheduled workflows on-demand from any branch
- Debugging workflow issues without polluting main

## Key Insight

The `--ref` flag tells GitHub to:
1. Use the workflow file from the specified branch
2. Run the workflow in the context of that branch
3. Include all changes from that branch

This means workflow changes can be tested iteratively without merging.

## Anti-pattern to Avoid

NEVER say:
- "I can't test this workflow until it's merged to main"
- "The workflow needs to be on main first"
- "Let me merge to main so I can run the workflow"

ALWAYS try `--ref <branch-name>` first.

## Related

- [workflow-authorization-testable-pattern](workflow-authorization-testable-pattern.md)
- [workflow-false-positive-verdict-parsing-2025-12-28](workflow-false-positive-verdict-parsing-2025-12-28.md)
- [workflow-false-positive-verdict-parsing-fix-2025-12-28](workflow-false-positive-verdict-parsing-fix-2025-12-28.md)
- [workflow-patterns-batch-changes-reduce-cogs](workflow-patterns-batch-changes-reduce-cogs.md)
- [workflow-patterns-composite-action](workflow-patterns-composite-action.md)
