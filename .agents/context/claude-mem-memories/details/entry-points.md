## Entry points

`import_claude_mem_memories.py`: globs `memories/*.json`, `npx tsx` per file; `--importer` > `$CLAUDE_MEM_IMPORTER` > plugin default.
`export_claude_mem_memories.py`: positional query, `--output-file`, `--session-number`, `--topic`.
`export_claude_mem_full_backup.py`: query `.`, `--project`, `--output-file`.
`export_claude_mem_direct.py`: `--project`, `--output-file`; reads the plugin's home-dir SQLite DB via `sqlite3`.
