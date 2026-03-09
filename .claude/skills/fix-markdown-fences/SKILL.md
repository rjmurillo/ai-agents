---
name: fix-markdown-fences
version: 1.1.0
model: claude-haiku-4-5
description: "Repair malformed markdown code fence closings. Use when markdown files have closing fences with language identifiers or when generating markdown with code blocks to ensure proper fence closure."
license: MIT
---

# Fix Markdown Code Fence Closings

Scan and repair malformed closing fences in markdown files. Closing fences must never contain language identifiers.

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `fix markdown fences` | Scan and repair malformed fence closings |
| `repair code block closings` | Fix closing fences with language identifiers |
| `markdown rendering broken` | Diagnose and fix fence issues |
| `code blocks bleeding into content` | Fix unclosed or malformed fences |
| `validate markdown code blocks` | Check all fences for correctness |

## Quick Reference

| Symptom | Cause | Fix |
|---------|-------|-----|
| Code block bleeds into text | Closing fence has language identifier | Remove identifier from closing fence |
| Nested blocks render wrong | Missing closing fence before new opening | Insert closing fence |
| Content cut off at end of file | Unclosed code block | Append closing fence |

## When to Use

**Use this skill when:**

- Markdown code blocks render incorrectly or bleed into surrounding content
- Closing fences have language identifiers (e.g., ` ```python ` instead of ` ``` `)
- Validating markdown documentation before committing

**Use manual editing instead when:**

- The issue is indentation or content inside the code block (not the fences)
- You need to change the language identifier on opening fences

## Process

Track fence state while scanning line by line:

1. **Detect opening fence**: Line matches the opening pattern below outside a block. Record indent level and enter "inside block" state.
2. **Detect malformed closing fence**: While inside a block, line matches the malformed closing pattern below. Insert a proper closing fence before this line.
3. **Detect valid closing fence**: Line matches the valid closing pattern below. Exit "inside block" state.

Regex patterns:

````regex
^\s*```[\w+-]+
^\s*```[\w+-]+\s*$
^\s*```\s*$
````

- [ ] No closing fences contain language identifiers
- [ ] Markdown renders correctly in preview
- [ ] `git diff` shows only fence-closing changes, no content modifications

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Manually searching for bad fences | Error-prone in large files | Use the algorithm or grep pattern |
| Copying opening fence line to close a block | Creates the exact bug this skill fixes | Always use plain ` ``` ` for closing |
| Fixing fences without tracking block state | Misidentifies nested vs sequential blocks | Use the stateful line-by-line algorithm |

## Prevention

When generating markdown with code blocks:

1. Always use plain \`\`\` for closing fences
2. Never copy the opening fence line to close
3. Track block state when programmatically generating markdown

<details>
<summary><strong>Implementation: Python (Recommended)</strong></summary>

```python
import re
from pathlib import Path

def fix_markdown_fences(content: str) -> str:
    """Fix malformed code fence closings in markdown content."""
    lines = content.splitlines()
    result = []
    in_code_block = False
    block_indent = ""

    opening_pattern = re.compile(r'^(\s*)```(\w+)')
    closing_pattern = re.compile(r'^(\s*)```\s*$')

    for line in lines:
        opening_match = opening_pattern.match(line)
        closing_match = closing_pattern.match(line)

        if opening_match:
            if in_code_block:
                result.append(f"{block_indent}```")
            result.append(line)
            block_indent = opening_match.group(1)
            in_code_block = True
        elif closing_match:
            result.append(line)
            in_code_block = False
            block_indent = ""
        else:
            result.append(line)

    if in_code_block:
        result.append(f"{block_indent}```")

    return '\n'.join(result)


def fix_markdown_files(directory: Path, pattern: str = "**/*.md") -> list[str]:
    """Fix all markdown files in directory. Returns list of fixed files."""
    fixed = []
    for file_path in directory.glob(pattern):
        content = file_path.read_text()
        fixed_content = fix_markdown_fences(content)
        if content != fixed_content:
            file_path.write_text(fixed_content)
            fixed.append(str(file_path))
    return fixed
```

</details>

<details>
<summary><strong>Implementation: Bash (Quick Check)</strong></summary>

```bash
# Find files with potential issues
grep -rEn -- '```\w+' --include="*.md" . | grep -vE "^[^:]*:[0-9]*:[[:space:]]*```\w+[[:space:]]*$"
```

</details>

<details>
<summary><strong>Implementation: PowerShell</strong></summary>

```powershell
$directories = @('docs', 'src')

foreach ($dir in $directories) {
    Get-ChildItem -Path $dir -Filter '*.md' -Recurse | ForEach-Object {
        $file = $_.FullName
        $content = Get-Content $file -Raw
        $lines = $content -split "`r?`n"
        $result = @()
        $inCodeBlock = $false
        $codeBlockIndent = ""

        for ($i = 0; $i -lt $lines.Count; $i++) {
            $line = $lines[$i]

            if ($line -match '^(\s*)```(\w+)') {
                if ($inCodeBlock) {
                    $result += $codeBlockIndent + '```'
                    $result += $line
                    $codeBlockIndent = $Matches[1]
                } else {
                    $result += $line
                    $codeBlockIndent = $Matches[1]
                    $inCodeBlock = $true
                }
            }
            elseif ($line -match '^(\s*)```\s*$') {
                $result += $line
                $inCodeBlock = $false
                $codeBlockIndent = ""
            }
            else {
                $result += $line
            }
        }

        if ($inCodeBlock) {
            $result += $codeBlockIndent + '```'
        }

        $newContent = $result -join "`n"
        Set-Content -Path $file -Value $newContent -NoNewline
        Write-Host "Fixed: $file"
    }
}
```

</details>

<details>
<summary><strong>Edge Cases Handled</strong></summary>

1. **Nested indentation**: Preserves indent level from opening fence
2. **Multiple consecutive blocks**: Each block tracked independently
3. **File ending inside block**: Automatically closes unclosed blocks
4. **Mixed line endings**: Accepts both `\n` and `\r\n` as input (normalizes output to `\n`)

</details>
