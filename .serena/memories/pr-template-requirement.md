# PR Template Requirement

## Rule

When creating a pull request, **always use the PR template** at `.github/PULL_REQUEST_TEMPLATE.md`.

## Template Location

```text
.github/PULL_REQUEST_TEMPLATE.md
```

## Required Sections

1. **Summary** - Brief description of changes
2. **Specification References** - Table with Issue, Spec references
3. **Changes** - Bulleted list of changes
4. **Type of Change** - Checkboxes (bug fix, feature, breaking, docs, infra, refactor)
5. **Testing** - Checkboxes (tests added, manual testing, no testing required)
6. **Agent Review** - Security review and other agent reviews
7. **Checklist** - Code quality checklist
8. **Related Issues** - Links to related issues

## How to Apply

Read the template before creating PR body:

```bash
cat .github/PULL_REQUEST_TEMPLATE.md
```

Then structure the PR body to match all sections.

## Common Mistakes to Avoid

- Do NOT create custom PR descriptions without the template sections
- Do NOT skip the Specification References table
- Do NOT forget the Type of Change checkboxes
