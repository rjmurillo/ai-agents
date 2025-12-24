# GraphQL Troubleshooting

**Statement**: Common GraphQL errors and fixes for gh CLI

**Context**: Debugging failed GraphQL mutations

**Atomicity**: 88%

**Impact**: 7/10

## Syntax Errors

**Problem**: `Parse error on "mutation" (error)`

**Cause**: Multi-line formatted query

**Fix**: Convert to single-line format (see graphql-mutation-format)

## Variable Type Errors

**Problem**: `Variable $id of type String! was provided invalid value`

**Cause**: Variable type mismatch

**Fix**: Verify variable types in mutation signature

```bash
# ID! expects node ID (e.g., PRRT_xxx), not numeric
-f id="PRRT_kwDO..." # Correct
-f id="12345"        # Wrong
```

## Authentication Errors

**Problem**: `Your token has not been granted the required scopes`

**Cause**: Insufficient token permissions

**Fix**: Ensure token has required scopes:

- `repo` for repository operations
- `write:discussion` for comments/reactions

## References

- [GitHub GraphQL API](https://docs.github.com/en/graphql)
- [GraphQL Explorer](https://docs.github.com/en/graphql/overview/explorer)
