# jq: Basic Field Extraction

## Skill-JQ-001

**Statement**: Use `.field` syntax for object access; `.[]` for array iteration.

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
