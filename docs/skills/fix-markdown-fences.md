# fix-markdown-fences

Finds and repairs malformed closing fences in markdown. It fixes a closing fence that carries a language name (which makes a code block bleed into the text after it) and a block left open at the end of a file.

## When to use it

- A code block renders wrong or bleeds into the prose below it.
- A closing fence has a language identifier, such as a closer written as `python` instead of a bare fence.
- You want to validate markdown fences before you commit.
- Trigger phrases: `fix markdown fences`, `repair code block closings`, `markdown rendering broken`, `code blocks bleeding into content`, `validate markdown code blocks`.

## When not to use it

- You want to check whether docs are accurate or examples compile: use [`doc-accuracy`](doc-accuracy.md) instead.
- The problem is indentation or content inside a block, or you need to change a language on an opening fence: edit by hand.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:fix-markdown-fences`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the fix-markdown-fences skill to check docs/ for malformed code fences and show me the defects before you change anything.
```

The skill runs the script in report mode first. It lists each defect as `FILE:LINE: KIND: TEXT`. It writes changes only after you agree.

## What you get

- A defect report with two kinds: `malformed_closing` (a closing fence with an info string) and `unclosed_block` (a file that ends inside a block).
- With `--write`, repaired files. A re-run on a clean tree exits `0`.
- A refusal list when `--write` would make a file worse.

Exit codes:

| Code | Meaning |
| --- | --- |
| `0` | No defects found, or `--write` repaired every defect |
| `1` | Report mode found defects, or `--write` refused at least one file |
| `2` | A path does not exist, or a file could not be read or written |

## Advanced use

From the root of a checkout of this repository:

```bash
uv run python .claude/skills/fix-markdown-fences/scripts/fix_fences.py --help
uv run python .claude/skills/fix-markdown-fences/scripts/fix_fences.py docs/
uv run python .claude/skills/fix-markdown-fences/scripts/fix_fences.py docs/guide.md --write
uv run python .claude/skills/fix-markdown-fences/scripts/fix_fences.py docs/ --json --pattern "*.md"
```

Flags: `--write` repairs in place, `--json` emits machine-readable output (never cut), `--pattern` sets the glob for directory scans (default `*.md`), and `--max-lines` bounds the text listing (default 200, `0` lists all). With no path, the script scans the current directory. It skips `.git`, `node_modules`, `.venv`, `venv`, and `__pycache__`.

Fence matching follows CommonMark. A closing fence uses the same character and is at least as long as the opener, so a three-backtick example inside a four-backtick container stays literal text. Files are read and written as bytes, so CRLF and CR line endings, a UTF-8 BOM, and a missing trailing newline all survive. Repair is idempotent.

Repair is best effort on ambiguous files. When a cluster of defects sits inside docs that show fenced markdown, the author usually wanted a wider container fence. Widen the container by hand instead of using `--write`.

**Write guard.** Before `--write` replaces a file, it refuses the file in two cases: a fence-looking line sits inside a raw HTML block, or the repair would turn a balanced file into an unclosed one. The second check uses `markdown-it-py` and is skipped, with a note on stderr, when that package is not installed. Refused files appear on a `Refused` line and need a manual fix. Other files in the same run are still repaired.

The skill lists known gaps, such as fences inside blockquotes, which the scanner does not see. Review `git diff` after a write and confirm only fence lines moved.

Chaining: [`doc-accuracy`](doc-accuracy.md) calls this skill to repair malformed fences it finds. The skill runs on the `haiku` model tier because the work is mechanical.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`doc-accuracy`](doc-accuracy.md): verifies doc claims and calls this skill for fence repairs.
- Source: [`SKILL.md`](../../src/claude/skills/fix-markdown-fences/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
