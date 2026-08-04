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

## Fixing Existing PRs

Write the body to a file and apply it with `--body-file`:

```bash
gh pr edit <N> --body-file <path>
```

`--body-file` sends the file byte for byte. The older
`gh api ... -f body="$(cat file)"` form in this memory's history worked, but command
substitution strips every trailing newline, so a body ending in a fenced block loses
its final blank line:

```bash
$ printf 'a\n\n```\ncode\n```\n\n' > b.md; wc -c < b.md          # 24
$ v="$(cat b.md)"; printf '%s' "$v" | wc -c                     # 22
```

Two bytes is cosmetic on its own. It matters because it makes a round trip lossy: read
the body, edit it, write it back, and the file shrinks each pass. Use `--body-file`.

Note for the record: command substitution does **not** re-expand backticks or `$` in
the file's contents. A quoted `"$(cat f)"` passes them through literally. An earlier
version of this memory claimed otherwise and was wrong.

## These sections are advisory, not blocking

Missing sections here produce `TEMPLATE_STATUS=WARN`, which
`scripts/ci/build_pr_validation_report.py` appends to `warnings` and never
promotes to `status`. A template WARN does not red the `Validate PR` check.

Use the template because it makes PRs readable, not because CI forces it. When the
check is actually red, the cause is a different signal. See
[ci-validate-pr-is-many-gates-only-some-read-the-body](../ci/ci-validate-pr-is-many-gates-only-some-read-the-body.md).

## Related

- [pr-156-review-findings](pr-156-review-findings.md)
- [pr-320c2b3-refactoring-analysis](pr-320c2b3-refactoring-analysis.md)
- [pr-52-retrospective-learnings](pr-52-retrospective-learnings.md)
- [pr-52-symlink-retrospective](pr-52-symlink-retrospective.md)
- [pr-753-remediation-learnings](pr-753-remediation-learnings.md)
