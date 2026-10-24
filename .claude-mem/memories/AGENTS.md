# .claude-mem/memories/

Committed claude-mem exports; three export wrappers in `.claude-mem/scripts/`.

## Matters

No import wrapper ships here (issue #5583, owner decision D21 (2026-10-24)); full `direct-backup-*.json` exports stay local.
Hand-maintained; not in `build_all.py` OWNED_PREFIXES.
Contract: `tests/claude_mem/`, `tests/test_claude_mem_scripts.py`.

## Entry points

`export_claude_mem_memories.py`: positional query, `--output-file`, `--session-number`, `--topic`.
`export_claude_mem_full_backup.py`: query `.`, `--project`, `--output-file`.
`export_claude_mem_direct.py`: `--project`, `--output-file`; reads the plugin's home-dir SQLite DB via `sqlite3`.

## Where to look

| Path | Why |
| --- | --- |
| `.agents/governance/MEMORY-MANAGEMENT.md` | Usage surface; `python3` calls are stale |

## Skip

Local `direct-backup-*.json` files here are gitignored full exports, many MB: grep or jq only.

## Constraints

`--output-file` outside `.claude-mem/memories/` exits 1 (CWE-22 guard).
markdownlint, `stale_script_refs.py`, `check_doc_interpreter_portability.py` skip this tree; dash and path gates do not.

## Dangerous assumptions

Default export filenames differ per script.

## Dependencies

`npx` + `tsx` and the thedotmack plugin (two scripts); `sqlite3` (direct only).
Exports run `scripts/review_memory_export_security.py`; nonzero blocks.

## Architecture

Two shims over plugin TypeScript; direct reads SQLite.

## Commands

```bash
uv run python .claude-mem/scripts/export_claude_mem_memories.py "<query>" --topic <topic>
uv run pytest tests/claude_mem/ tests/test_claude_mem_scripts.py -x
```
