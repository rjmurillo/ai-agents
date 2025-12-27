# Skill-Edit-002: Unique Context for Edit Matching

**Statement**: Include surrounding context in old_string to ensure unique matching when target content appears multiple times.

**Context**: When editing content that may appear multiple times in a file.

**Evidence**: Edit tool requires old_string to be unique in the file or the edit fails.

**Atomicity**: 95%

**Tag**: helpful (prevents ambiguous edit failures)

**Impact**: 8/10 (common editing scenario)

**Created**: 2025-12-20

**Problem**:

```text
# WRONG - Generic pattern that appears multiple times
Edit(file_path="file.md", old_string="return null;", new_string="return undefined;")
# Error: old_string matches multiple locations
```

**Solution**:

```text
# CORRECT - Include unique surrounding context
Edit(file_path="file.md",
  old_string="function getValue() {\n  return null;\n}",
  new_string="function getValue() {\n  return undefined;\n}")
```

**Why It Matters**:

The edit tool cannot proceed if `old_string` matches multiple locations because it cannot determine which occurrence to replace. Including surrounding context (function name, preceding comment, enclosing block) makes the match unique.

**Pattern**:

```text
# When editing repeated patterns, include:
# - Function/method signature
# - Preceding comment
# - Surrounding lines
# - Enclosing braces/block
```

**Anti-Pattern**:

```text
# Minimal pattern that may repeat
old_string="const x = 1"

# Better: Include full statement context
old_string="// Initialize counter\nconst x = 1;"
```

**Validation**: 1 (common pattern across sessions)

**Related Skills**:

- Skill-Verification-003: Verify artifact state matches API response before modifications

**Source**: Edit Skills (2025-12-20)
