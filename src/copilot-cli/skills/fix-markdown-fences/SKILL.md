---
name: fix-markdown-fences
version: 1.2.0
model: haiku
model-rationale: cost. The 'haiku' rolling alias resolves via the platform model_tiers map to a tier priced below the sonnet-tier harness default; this unit is routing/mechanical work where the cheaper tier suffices (ADR-080 rule 3).
description: >-
  Repair malformed markdown code fence closings. Use when you say "fix markdown
  fences", "repair code block closings", "markdown rendering broken", "code
  blocks bleeding into content", or "validate markdown code blocks" on any .md
  file. Do NOT use for documentation accuracy checks or verifying code examples
  (use doc-accuracy).
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

Do not walk the file by hand. Fence tracking is a state machine, and
`scripts/fix_fences.py` runs it.

1. **Report.** Run the script over the target path. It prints every defect as
   `FILE:LINE: KIND: TEXT` and exits 1 when it finds any.

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/fix-markdown-fences/scripts/fix_fences.py" FILE_OR_DIR
```

2. **Read the report.** Two kinds appear:
   - `malformed_closing`: a closing fence carries a language identifier, so
     the block bleeds into the following prose.
   - `unclosed_block`: the file ends with a block still open.

3. **Decide, then write.** Repair is best-effort on an ambiguous file. When a
   defect cluster sits inside documentation that shows fenced markdown, the
   author usually wanted a wider container fence (four backticks around a
   three-backtick example), not the closing fence the repair inserts. Widen
   the container by hand in that case. Otherwise:

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/fix-markdown-fences/scripts/fix_fences.py" FILE_OR_DIR --write
```

4. **Confirm.** Re-run step 1. A clean tree exits 0. Then read `git diff` and
   confirm only fence lines moved.

## Scripts

### scripts/fix_fences.py

Detects and repairs malformed fence closings. Reporting is the default;
`--write` is required to modify a file.

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/fix-markdown-fences/scripts/fix_fences.py" PATH [PATH ...]
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/fix-markdown-fences/scripts/fix_fences.py" PATH --write
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/fix-markdown-fences/scripts/fix_fences.py" PATH --json
```

Options: `--write` repairs in place, `--json` emits machine-readable output,
`--pattern` sets the glob for directory scans (default `*.md`). Paths default
to the current directory. `.git`, `node_modules`, `.venv`, and `__pycache__`
are skipped.

Fence matching follows CommonMark, which is what keeps the tool from damaging
documentation:

- A fence is three or more backticks or three or more tildes.
- A closing fence uses the same character and is at least as long as the
  opener, so a three-backtick example nested inside a four-backtick container
  stays literal text.
- A backtick opening fence whose info string contains a backtick is not a
  fence.

Line endings and the trailing newline are preserved. Repair is idempotent.

Exit codes (ADR-035):

- `0` no defects found, or `--write` repaired every defect it found
- `1` report mode found at least one defect; nothing was written
- `2` a requested path does not exist, or a file could not be read or written

## Reference: the algorithm

Kept so a reader can audit the script, not so the agent can run it by hand.

Track fence state while scanning line by line:

1. **Detect opening fence**: outside a block, a line of three or more
   backticks or tildes opens one. Record the character, the length, and the
   indent.
2. **Detect malformed closing fence**: inside a block, a line using the same
   character at the same length or longer, carrying a non-empty info string.
   Insert a bare closing fence before it.
3. **Detect valid closing fence**: the same character at the same length or
   longer with an empty info string. Exit the block.
4. **At end of file**: a still-open block gets a bare closing fence appended.

## Verification

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/fix-markdown-fences/scripts/fix_fences.py" PATH
echo "exit=$?"   # 0 = clean, 1 = defects found, 2 = bad input
```

- [ ] The script exits 0 on the repaired path.
- [ ] `git diff` shows only fence lines added, no content modifications.
- [ ] Defects that belong inside a wider container fence were widened by
      hand rather than closed by `--write`.

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Manually searching for bad fences | Error-prone in large files, and the agent cannot track fence length by eye | Run `scripts/fix_fences.py` |
| Simulating the state machine in-context | The script already does it, exactly and for free | Read the script's report |
| Running `--write` across a whole repo unreviewed | A repair inside nested documentation is often the wrong fix | Report first, review, then write per path |
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
grep -rEn --include="*.md" -- '```\w+' . | grep -vE "^[^:]*:[0-9]*:[[:space:]]*```\w+[[:space:]]*$"
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
3. **File ending inside block**: Closes an unclosed block with a fence of the same character and length
4. **Mixed line endings**: `\n` and `\r\n` are both accepted and preserved, as is the presence or absence of a trailing newline

</details>
