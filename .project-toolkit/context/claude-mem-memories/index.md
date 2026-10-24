[.claude-mem/memories/]
|Committed claude-mem exports; three export wrappers in `.claude-mem/scripts/`. (see: .project-toolkit/context/claude-mem-memories/details/claude-memmemories.md)
[Matters]
|No import wrapper ships here (issue #5583, owner decision D21 (2026-10-24)); ... (see: .project-toolkit/context/claude-mem-memories/details/matters.md)
[Entry points]
|`export_claude_mem_memories.py`: positional query, `--output-file`, `--sessio... (see: .project-toolkit/context/claude-mem-memories/details/entry-points.md)
[Where to look]
|| Path | Why | (see: .project-toolkit/context/claude-mem-memories/details/where-to-look.md)
[Skip]
|Nothing. The directory holds `AGENTS.md`, `README.md`, and any committed topi... (see: .project-toolkit/context/claude-mem-memories/details/skip.md)
[Constraints]
|`--output-file` outside `.claude-mem/memories/` exits 1 (CWE-22 guard). (see: .project-toolkit/context/claude-mem-memories/details/constraints.md)
[Dangerous assumptions]
|Default export filenames differ per script. (see: .project-toolkit/context/claude-mem-memories/details/dangerous-assumptions.md)
[Dependencies]
|`npx` + `tsx` and the thedotmack plugin (two scripts); `sqlite3` (direct only). (see: .project-toolkit/context/claude-mem-memories/details/dependencies.md)
[Architecture]
|Two shims over plugin TypeScript; direct reads SQLite. (see: .project-toolkit/context/claude-mem-memories/details/architecture.md)
[Commands]
|(see detail file) (see: .project-toolkit/context/claude-mem-memories/details/commands.md)