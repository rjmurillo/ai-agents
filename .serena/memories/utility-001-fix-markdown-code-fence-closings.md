# Utility: Fix Markdown Code Fence Closings

## Skill-Utility-001: Fix Markdown Code Fence Closings

- **Atomicity**: 92%
- **Location**: `.agents/utilities/fix-markdown-fences/`
- **Implementations**: Python (`fix_fences.py`), PowerShell (`fix_fences.ps1`)

### Problem

When generating markdown with code blocks, closing fences sometimes include language identifiers:

```markdown
<!-- Wrong -->
` ` `python
def hello():
    pass
` ` `python  <!-- Should be just ``` -->

<!-- Correct -->
` ` `python
def hello():
    pass
` ` `
```

### When to Use

1. After generating markdown with multiple code blocks
2. When fixing existing markdown files with rendering issues
3. When code blocks appear to "bleed" into surrounding content
4. As a validation step before committing markdown documentation

### Algorithm

1. **Opening fence**: Line matches `^\s*` ` `\w+` and not inside block. Enter "inside block" state.
2. **Malformed closing fence**: Line matches `^\s*` ` `\w+` while inside block. Insert proper closing fence before this line.
3. **Valid closing fence**: Line matches `^\s*` ` `\s*$`. Exit "inside block" state.
4. **End of file**: If still inside block, append closing fence.

### Usage

```bash
# PowerShell
pwsh .agents/utilities/fix-markdown-fences/fix_fences.ps1

# Python
python .agents/utilities/fix-markdown-fences/fix_fences.py
```

### Edge Cases Handled

- Nested indentation: Preserves indent level from opening fence
- Multiple consecutive blocks: Each block tracked independently
- File ending inside block: Automatically closes unclosed blocks
- Mixed line endings: Handles both `\n` and `\r\n`

### Prevention

When generating markdown with code blocks:

1. Always use plain ` ` ` for closing fences
2. Never copy the opening fence line to close
3. Track block state when programmatically generating markdown

---