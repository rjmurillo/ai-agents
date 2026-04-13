# Skill-implementation-008: Verbatim Patch Mode

**Statement**: When user provides code patch, apply EXACTLY as written without interpretation or improvement.

**Context**: User-provided patches represent the correct solution. Agent should not reinterpret, optimize, or improve the patch. Apply patch character-for-character as provided.

**Evidence**: PR #760 user provided patches 3 times before agent applied correctly. Agent was modifying patches or reinterpreting the pattern, causing user to provide patches again. Final success (commit ddf7052) came from applying user patch verbatim without changes.

**Atomicity**: 96% | **Impact**: 8/10

## Pattern

When user provides code patch in comment or message:

1. **Copy patch exactly** - character-for-character, no modifications
2. **Apply without interpretation** - don't try to "improve" or optimize
3. **Preserve user's formatting** - indentation, comments, structure as-is
4. **Document source** - comment indicating patch source ("User-provided patch from issue #760")
5. **Test** - verify patch applies cleanly and tests pass

If patch seems incorrect or suboptimal, ASK before applying:
- "Should I apply this patch as-is, or would you like me to suggest modifications first?"

User knows correct fix. Agent should not second-guess.

## Anti-Pattern

Never apply user patch with modifications:
- "Improving" the code style
- Optimizing variable names
- Reordering statements
- Adding extra error handling
- Removing comments

This signals agent doesn't trust user's solution and forces re-iteration.

## Related

- [implementation-001-memory-first-pattern](implementation-001-memory-first-pattern.md)
- [implementation-001-pre-implementation-test-discovery](implementation-001-pre-implementation-test-discovery.md)
- [implementation-002-test-driven-implementation](implementation-002-test-driven-implementation.md)
- [implementation-006-graphql-first](implementation-006-graphql-first.md)
- [implementation-additive-approach](implementation-additive-approach.md)
