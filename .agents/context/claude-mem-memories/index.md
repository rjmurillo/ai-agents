[.claude-mem/memories/]
|Committed claude-mem exports; four wrappers in `.claude-mem/scripts/`. (see: .agents/context/claude-mem-memories/details/claude-memmemories.md)
[Matters]
|No hook or lefthook job imports these; import is manual. (see: .agents/context/claude-mem-memories/details/matters.md)
[Entry points]
|`import_claude_mem_memories.py`: globs `memories/*.json`, `npx tsx` per file;... (see: .agents/context/claude-mem-memories/details/entry-points.md)
[Where to look]
|| Path | Why | (see: .agents/context/claude-mem-memories/details/where-to-look.md)
[Skip]
|`README.md` here: dead `.ps1` and `scripts/*.ts` refs. (see: .agents/context/claude-mem-memories/details/skip.md)
[Constraints]
|`--output-file` outside `.claude-mem/memories/` exits 1 (CWE-22 guard). (see: .agents/context/claude-mem-memories/details/constraints.md)
[Dangerous assumptions]
|No plugin exits 0. ADR-035 deviation: blank `--importer`, bad path, or missin... (see: .agents/context/claude-mem-memories/details/dangerous-assumptions.md)
[Dependencies]
|`npx` + `tsx` and the thedotmack plugin (three scripts); `sqlite3` (direct on... (see: .agents/context/claude-mem-memories/details/dependencies.md)
[Architecture]
|Three shims over plugin TypeScript; direct reads SQLite. (see: .agents/context/claude-mem-memories/details/architecture.md)
[Commands]
|(see detail file) (see: .agents/context/claude-mem-memories/details/commands.md)