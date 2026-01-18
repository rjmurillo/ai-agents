# Jq: Basic Field Extraction

## Skill-JQ-001: Basic Field Extraction

**Statement**: Use `.field` syntax for object access; `.[]` for array iteration.

**Pattern**:

```bash
# Single field
echo '{"name": "test"}' | jq '.name'
# Output: "test"

# Nested field
echo '{"user": {"login": "octocat"}}' | jq '.user.login'
# Output: "octocat"

# Array iteration
echo '[{"id": 1}, {"id": 2}]' | jq '.[].id'
# Output:
# 1
# 2

# Specific array index
echo '[{"id": 1}, {"id": 2}]' | jq '.[0]'
# Output: {"id": 1}
```

**Atomicity**: 95%

---

## Related

- [jq-002-raw-output-mode](jq-002-raw-output-mode.md)
- [jq-003-object-construction](jq-003-object-construction.md)
- [jq-004-filtering-with-select](jq-004-filtering-with-select.md)
- [jq-005-array-operations](jq-005-array-operations.md)
- [jq-006-string-interpolation](jq-006-string-interpolation.md)
