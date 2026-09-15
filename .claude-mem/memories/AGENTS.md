# .claude-mem/memories/

Committed claude-mem exports; four wrappers in `.claude-mem/scripts/`.

## Matters

No hook or lefthook job imports these; import is manual.
Hand-maintained; not in `build_all.py` OWNED_PREFIXES.
Contract: `tests/claude_mem/`, `tests/test_claude_mem_scripts.py`.

## Entry points

`import_claude_mem_memories.py`: globs `memories/*.json`, `npx tsx` per file; `--importer` > `$CLAUDE_MEM_IMPORTER` > plugin default.
`export_claude_mem_memories.py`: positional query, `--output-file`, `--session-number`, `--topic`.
`export_claude_mem_full_backup.py`: query `.`, `--project`, `--output-file`.
`export_claude_mem_direct.py`: `--project`, `--output-file`; reads the plugin's home-dir SQLite DB via `sqlite3`.

## Where to look

| Path | Why |
| --- | --- |
| `.agents/governance/MEMORY-MANAGEMENT.md` | Usage surface; `python3` calls and "Auto-import" step are stale |

## Skip

`README.md` here: dead `.ps1` and `scripts/*.ts` refs.
Committed `direct-backup-*.json`: 9.6MB; grep or jq only.

## Constraints

`--output-file` outside `.claude-mem/memories/` exits 1 (CWE-22 guard).
markdownlint, `stale_script_refs.py`, `check_doc_interpreter_portability.py` skip this tree; dash and path gates do not.

## Dangerous assumptions

No plugin exits 0. ADR-035 deviation: blank `--importer`, bad path, or missing `npx` exit 1, not 2.
Default export filenames differ per script.

## Dependencies

`npx` + `tsx` and the thedotmack plugin (three scripts); `sqlite3` (direct only).
Exports run `scripts/review_memory_export_security.py`; nonzero blocks.

## Architecture

Three shims over plugin TypeScript; direct reads SQLite.

## Commands

```bash
uv run python .claude-mem/scripts/import_claude_mem_memories.py
uv run python .claude-mem/scripts/export_claude_mem_memories.py "<query>" --topic <topic>
uv run pytest tests/claude_mem/ tests/test_claude_mem_scripts.py -x
```
