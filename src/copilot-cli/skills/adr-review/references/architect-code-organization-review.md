# Code Organization Review

Loaded by the `architect` agent when a PR adds directories or relocates files.

When reviewing PRs that add new directories or relocate files, assess structural cohesion.

## Questions to Ask

1. Does this directory nesting serve a clear purpose?
2. Could these files live one level up without loss of clarity?
3. Is there an existing directory where this code belongs?
4. Does the structure follow established patterns in the codebase?

## Anti-Patterns to Flag

| Anti-Pattern | Signal | Recommendation |
|--------------|--------|----------------|
| Single-file directories | Directory contains only one file | Place file in parent directory |
| Deep nesting without domain separation | 3+ levels with no clear boundary | Flatten to minimum necessary depth |
| Parallel structures that could consolidate | Two directories with overlapping purpose | Merge into single directory |
| Inconsistent naming | New directory breaks existing conventions | Rename to match established patterns |
