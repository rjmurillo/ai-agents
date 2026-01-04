# Memory Documentary

Generate evidence-based documentary reports by searching across all memory systems.

## Usage

```bash
/memory-documentary [topic]
```

## Arguments

- `topic` (required): The subject to analyze across memory systems

## Examples

```bash
/memory-documentary "recurring frustrations"
/memory-documentary "coding patterns not codified"
/memory-documentary "evolution of thinking on testing"
/memory-documentary "decisions I second-guessed"
```

## Execution

This command invokes the memory-documentary skill which:

1. Searches ALL 4 MCP servers (Claude-Mem, Forgetful, Serena, DeepWiki)
2. Searches .agents/ directory artifacts
3. Searches docs/ directory artifacts
4. Searches GitHub issues (open and closed)
5. Searches GitHub pull requests (open and closed)
6. Generates documentary-style report with full evidence chains
7. Updates memories with discovered meta-patterns

## Output

Report saved to: `.agents/analysis/[topic]-documentary-[date].md`

## Related Commands

- `/memory-search` - Simple memory search
- `/memory-explore` - Knowledge graph traversal
