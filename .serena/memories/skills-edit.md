# Edit Skills

**Extracted**: 2025-12-20
**Source**: PR #212 retrospective analysis

## Skill-Edit-001: Read-before-Edit Pattern

**Statement**: Always read the current file state before attempting edits to ensure accurate matching.

**Context**: When modifying files using edit tools that require exact string matching.

**Evidence**: PR #212 - Edit operations failed when old_string didn't match current content; reading first prevented all failures.

**Atomicity**: 98%

**Tag**: helpful (prevents edit failures)

**Impact**: 10/10 (fundamental for reliable editing)

**Created**: 2025-12-20

**Problem**:

```text
# WRONG - Edit without reading current state
Edit(file_path="file.md", old_string="expected content", new_string="replacement")
# Fails if file was modified since last read or if content differs from expectation
```

**Solution**:

```text
# CORRECT - Read first, then edit with exact match
Read(file_path="file.md")
# Observe actual content, then use exact string for old_string
Edit(file_path="file.md", old_string="actual content from read", new_string="replacement")
```

**Why It Matters**:

Edit tools require exact string matching for `old_string`. If the file has been modified since you last read it, or if you're working from memory of what the content should be, the edit will fail. Always reading the current state ensures:

1. You have the exact current content
2. You can see any changes made by other processes
3. Your `old_string` will match exactly

**Pattern**:

```text
# Before any edit operation
1. Read(file_path) - Get current content
2. Identify exact substring to replace
3. Edit(file_path, old_string=exact_match, new_string=replacement)
4. Optionally verify with another Read
```

**Anti-Pattern**:

```text
# Editing from memory or assumption
Edit(file_path, old_string="what I think it says", ...)

# Editing without reading after long delay
[many operations later]
Edit(file_path, old_string="stale content from earlier", ...)
```

**Validation**: 1 (PR #212 - zero edit failures when pattern followed)

---

## Skill-Edit-002: Unique Context for Edit Matching

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

---

## Related Skills

- Skill-Verification-003: Verify artifact state matches API response before modifications
