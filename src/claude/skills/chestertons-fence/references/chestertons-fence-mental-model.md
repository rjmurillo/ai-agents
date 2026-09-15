---
source: wiki/concepts/Mental Models/Chestertons Fence.md
created: 2026-04-11
review-by: 2026-07-11
---

# Chesterton's Fence Mental Model

## Principle

Before removing or changing something, first understand why it exists.

> "Don't ever take a fence down until you know the reason it was put up." -- G.K. Chesterton

## Application to Code Investigation

- Before deleting code, understand its purpose
- Before removing a process, understand what problem it solved
- Before deprecating a service, understand its dependencies

## Anti-Pattern: Blind Removal

Removing "legacy" code or processes without understanding original constraints leads to:

- Reintroducing bugs that were previously fixed
- Breaking implicit dependencies
- Losing institutional knowledge

## Investigation Checklist

Before recommending REMOVE or REPLACE:

- [ ] Original purpose documented or discovered via git archaeology
- [ ] Current constraints compared to original constraints
- [ ] Downstream dependencies mapped
- [ ] Migration path defined (not just deletion)

## Related Models

| Model | Connection |
|-------|------------|
| Gall's Law | Complex systems evolved from simple ones |
| Second System Effect | Resist over-engineering replacements |
| Strangler Fig Pattern | Incremental migration respects existing behavior |
| Hyrum's Law | Changing observable behavior breaks unknown dependents |
