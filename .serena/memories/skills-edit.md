# Edit Tool Skills

**Created**: 2025-12-20
**Source**: PR #212 retrospective

## Skill-Edit-001: Read Before Edit Discipline

**Statement**: Call Read tool before Edit to ensure old_string matches file content exactly

**Context**: Before calling Edit tool on any file

**Evidence**: PR #212 - Edit failures resolved by reading file first

**Atomicity**: 98%

**Tag**: helpful (prevents edit failures)

**Impact**: 9/10 (eliminates failed edit attempts)

**Created**: 2025-12-20

**Problem**:

```python
# WRONG - Guessing old_string without reading file
Edit(
    file_path="file.md",
    old_string="expected content",  # May not match exactly
    new_string="new content"
)
# Result: Edit fails if old_string doesn't match
```

**Solution**:

```python
# CORRECT - Read file first, verify content, then edit
content = Read(file_path="file.md")
# Verify old_string exists in content
Edit(
    file_path="file.md",
    old_string="actual content from file",  # Exact match
    new_string="new content"
)
```

**Why It Matters**:

The Edit tool requires `old_string` to match file content exactly (including whitespace, line endings, indentation). Guessing the content without reading first leads to edit failures and wasted retry iterations.

**Pattern**:

```python
# Safe edit workflow
1. Read(file_path) - Get current content
2. Verify old_string exists and is unique
3. Edit(file_path, old_string, new_string)
```

**Anti-Pattern**:

```python
# Unsafe - edit without reading
Edit(file_path, guessed_old_string, new_string)
```

**Validation**: 1 (PR #212, multiple edit failures before adopting pattern)

---

## Edit Tool Best Practices

### 1. Exact Match Requirement

The `old_string` parameter must match file content EXACTLY:

- Same whitespace (spaces vs tabs)
- Same line endings (CRLF vs LF)
- Same indentation
- No extra/missing characters

### 2. Uniqueness Check

Before editing, verify `old_string` appears only once in the file:

```python
content = Read(file_path)
if content.count(old_string) > 1:
    # old_string is not unique - need more context
    # Expand old_string to include surrounding lines
```

### 3. Context Expansion

If `old_string` is not unique, expand it to include surrounding context:

```python
# Instead of:
old_string = "result = True"

# Use more context:
old_string = """def validate():
    result = True
    return result"""
```

### 4. Multi-Line Edits

For multi-line changes, include complete logical blocks:

```python
# Good - complete function
old_string = """def process():
    step1()
    step2()
    return result"""

new_string = """def process():
    step1()
    step2()
    step3()  # New step
    return result"""
```

### 5. Replace All Pattern

Use `replace_all=True` when renaming variables/functions across a file:

```python
Edit(
    file_path="module.py",
    old_string="oldFunctionName",
    new_string="newFunctionName",
    replace_all=True  # Replace all occurrences
)
```

---

## Common Edit Failures and Fixes

### Failure: "old_string not found in file"

**Cause**: Content doesn't match exactly

**Fix**:

1. Read the file
2. Copy exact content (including whitespace)
3. Use that as old_string

### Failure: "old_string appears multiple times"

**Cause**: old_string is not unique

**Fix**:

1. Expand old_string to include more context
2. Make it unique within the file

### Failure: "Line ending mismatch"

**Cause**: File uses CRLF, old_string uses LF (or vice versa)

**Fix**:

1. Read file to see actual line endings
2. Use same line endings in old_string

---

## Edit vs Write Decision Matrix

| Use Case | Tool | Rationale |
|----------|------|-----------|
| Modify existing file content | Edit | Safer - requires exact match |
| Create new file | Write | Only option |
| Replace entire file | Write (after Read) | Simpler than multiple Edits |
| Rename variable across file | Edit with replace_all=True | Targeted change |
| Add new section to file | Edit | Preserves surrounding content |
| Remove section from file | Edit | old_string = section, new_string = "" |

---

## Workflow Examples

### Example 1: Update Configuration Value

```python
# Step 1: Read file
config = Read("config.yaml")

# Step 2: Identify exact old content
# From read output, find:
# timeout: 30
# max_retries: 3

# Step 3: Edit with exact match
Edit(
    file_path="config.yaml",
    old_string="timeout: 30",
    new_string="timeout: 60"
)
```

### Example 2: Add Function to Module

```python
# Step 1: Read file to find insertion point
module = Read("utils.py")

# Step 2: Find unique anchor point (e.g., existing function)
# From read output:
# def existing_function():
#     return True

# Step 3: Edit to add after existing function
Edit(
    file_path="utils.py",
    old_string="""def existing_function():
    return True""",
    new_string="""def existing_function():
    return True


def new_function():
    return False"""
)
```

### Example 3: Rename Variable Across File

```python
# Step 1: Read to verify variable name
code = Read("module.py")

# Step 2: Verify variable exists
if "oldVarName" in code:
    # Step 3: Replace all occurrences
    Edit(
        file_path="module.py",
        old_string="oldVarName",
        new_string="newVarName",
        replace_all=True
    )
```

---

## Related Skills

- Skill-PowerShell-001: Variable interpolation safety
- Read tool: Always precedes Edit operations

## References

- PR #212: Edit failures before adopting read-first pattern
