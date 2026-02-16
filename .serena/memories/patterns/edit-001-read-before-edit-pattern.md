# Skill-Edit-001: Read-before-Edit Pattern

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

**Source**: Edit Skills (2025-12-20)
