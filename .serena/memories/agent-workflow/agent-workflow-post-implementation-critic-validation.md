# Evidence: convention drift caught after a claimed completion

<!-- placement: evidence; reason: records one incident where self-review missed a convention, not an operating contract -->

## Observed evidence

Session 87: after renaming `.claude/commands/pr-review.md`, the agent
claimed the work complete. The user invoked the critic, which found missing
numeric IDs against the naming convention. Fix commit `5a65f65` followed.
Self-review missed the compliance gap that an independent check caught.

## Migration disposition

The `build` skill's four exit gates (`code-qualities-assessment`,
`taste-lints`, `doc-accuracy`, `orphan-ref-validator`) and the `review` skill
own post-implementation convention checks. This memory keeps the session 87
incident as evidence for why those gates are preconditions, not advice.
