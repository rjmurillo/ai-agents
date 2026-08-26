---
name: fix-markdown-fences
version: 1.3.0
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
| Code block bleeds into text | Closing fence has language identifier | Insert a bare closing fence above it; the line then opens the next block |
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
`fix_fences.py` runs it.

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

### fix_fences.py

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
- A marker indented four or more spaces is an indented code block, not a
  fence. That is what stops a repair from appending a fence to a document
  that shows a bare fence inside an indented block. The cost is that a fence
  nested that deep inside a list item is invisible here: the tool declines to
  see a fence rather than inventing one, so it misses rather than corrupts.

Files are read and written as bytes, so CRLF and CR endings survive, a UTF-8
BOM survives, and the Unicode separators `str.splitlines` would swallow (form
feed, U+0085, U+2028, U+2029) stay put. Each line keeps its own terminator, so
a mixed-ending file is not normalized. Repair is idempotent.

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
| Manually searching for bad fences | Error-prone in large files, and the agent cannot track fence length by eye | Run `fix_fences.py` |
| Simulating the state machine in-context | The script already does it, exactly and for free | Read the script's report |
| Running `--write` across a whole repo unreviewed | A repair inside nested documentation is often the wrong fix | Report first, review, then write per path |
| Copying opening fence line to close a block | Creates the exact bug this skill fixes | Close with the opener's character, no info string, at least the opener's length |
| Fixing fences without tracking block state | Misidentifies nested vs sequential blocks | Run `fix_fences.py`, which tracks it |

## Prevention

When generating markdown with code blocks:

1. Close with the opener's fence character and no info string, at a length
   at least the opener's. A four-backtick container needs four to close it,
   which is what lets it hold a three-backtick example.
2. Never copy the opening fence line to close
3. Track block state when programmatically generating markdown

The shipped script does this for you; `fix_fences.py` is the
implementation, and the Reference section above is the algorithm it runs. An
earlier revision of this file inlined a copy of that parser here under
"Implementation: Python (Recommended)". It was the pre-CommonMark version,
which had no fence-length rule and so corrupted any document showing a
three-backtick example inside a four-backtick container. It is gone rather
than fixed: a second copy of a parser drifts from the one that ships.

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
4. **Mixed line endings**: `\n`, `\r\n` and `\r` are preserved per line, as is a UTF-8 BOM and the presence or absence of a trailing newline

</details>
