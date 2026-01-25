# Fix Markdown Code Fence Closings

**Statement**: Closing fences should not include language identifiers

**Context**: When generating markdown with code blocks

**Atomicity**: 92%

**Impact**: 7/10

**Location**: `.agents/utilities/fix-markdown-fences/`

## Problem

```markdown
<!-- Wrong -->
```python
def hello():
    pass
```python  <!-- Should be just ``` -->
```

## Algorithm

1. **Opening fence**: Line matches `^\s*` ` `\w+` and not inside block. Enter "inside block" state.
2. **Malformed closing fence**: Line matches `^\s*` ` `\w+` while inside block. Insert proper closing fence.
3. **Valid closing fence**: Line matches `^\s*` ` `\s*$`. Exit "inside block" state.
4. **End of file**: If still inside block, append closing fence.

## Usage

```bash
pwsh .agents/utilities/fix-markdown-fences/fix_fences.ps1
```

## When to Use

- After generating markdown with multiple code blocks
- When code blocks appear to "bleed" into surrounding content

## Related

- [utilities-cva-refactoring](utilities-cva-refactoring.md)
- [utilities-pathinfo-conversion](utilities-pathinfo-conversion.md)
- [utilities-precommit-hook](utilities-precommit-hook.md)
- [utilities-regex](utilities-regex.md)
- [utilities-security-patterns](utilities-security-patterns.md)
