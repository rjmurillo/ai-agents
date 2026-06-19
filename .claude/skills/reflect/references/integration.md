# Reflect Anti-Patterns and Integration

Load when wiring reflect into the session protocol, the memory skill, or Serena.

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Applying without showing | User loses visibility | Always preview changes |
| Overwriting existing learnings | Loses history | Append with timestamps |
| Generic observations | Not actionable | Be specific and contextual |
| Ignoring LOW confidence | Lose valuable patterns | Track for future validation |
| Creating memory for one-off | Noise | Wait for repeated patterns |

---

## Integration

### With Session Protocol

Run reflection at session end as part of retrospective:

```text
## Session End Checklist
- [ ] Complete session log
- [ ] Run skill reflection (if skills were used)
- [ ] Update Serena memory
- [ ] Commit changes
```

### With Memory Skill

Skill memories integrate with the memory system:

```bash
# Search skill sidecar learnings
python3 .claude/skills/memory/scripts/search_memory.py --query "github-observations constraints"

# Read specific skill sidecar
Read .serena/memories/github-observations.md
```

### With Serena

If Serena MCP is available:

```text
mcp__serena__read_memory(memory_file_name="github-observations")
mcp__serena__write_memory(memory_file_name="github-observations", memory_content="...")
```

