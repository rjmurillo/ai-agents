# Claude-Mem Export/Import Scripts Location

## Summary

The export-memories.ts and import-memories.ts scripts referenced in Claude-Mem documentation are installed with the claude-mem plugin and accessible via wrapper scripts in the ai-agents repository.

## Script Locations

### Installed Plugin Scripts (Source)

- **export-memories.ts**: `~/.claude/plugins/marketplaces/thedotmack/scripts/export-memories.ts`
- **import-memories.ts**: `~/.claude/plugins/marketplaces/thedotmack/scripts/import-memories.ts`

These are the actual implementation scripts installed with the claude-mem plugin.

### Project Wrapper Scripts (ai-agents)

- **export-memories.ts**: `scripts/export-memories.ts`
- **import-memories.ts**: `scripts/import-memories.ts`

These wrapper scripts forward all arguments to the installed plugin scripts, allowing the documented commands to work from the project root:

```bash
npx tsx scripts/export-memories.ts "[query]" output.json
npx tsx scripts/import-memories.ts input.json
```

## Wrapper Implementation

```typescript
#!/usr/bin/env tsx
import { spawn } from 'child_process';
import { join } from 'path';
import { homedir } from 'os';

const pluginScriptPath = join(
  homedir(),
  '.claude/plugins/marketplaces/thedotmack/scripts/export-memories.ts'
);

const args = process.argv.slice(2);
const child = spawn('npx', ['tsx', pluginScriptPath, ...args], {
  stdio: 'inherit',
  shell: true
});
```

## Why Wrappers Are Needed

1. **Plugin Location**: Scripts are in `~/.claude/plugins/`, not in the project
2. **Documentation Consistency**: Allows `npx tsx scripts/export-memories.ts` to work as documented
3. **Project Portability**: Works from any ai-agents clone without path changes
4. **Team Onboarding**: New team members don't need to know plugin installation paths

## Usage Examples

All commands work from project root:

```bash
# Export session memories
npx tsx scripts/export-memories.ts "session 229" \
  .claude-mem/memories/2026-01-03-session-229.json

# Import shared memories  
npx tsx scripts/import-memories.ts \
  .claude-mem/memories/2026-01-03-shared.json

# Export by project
npx tsx scripts/export-memories.ts "" all.json --project=ai-agents
```

## Source Repository

The original scripts are part of the claude-mem plugin:
- **GitHub**: https://github.com/thedotmack/claude-mem/tree/main/scripts
- **Documentation**: https://docs.claude-mem.ai/usage/export-import

## Integration Points

- `.claude-mem/memories/README.md` - Documents wrapper script location
- `.agents/governance/MEMORY-MANAGEMENT.md` - Uses wrapper commands
- `.agents/SESSION-PROTOCOL.md` - References wrapper commands

## Troubleshooting

### "scripts/export-memories.ts not found"

Verify wrapper scripts exist:
```bash
ls -l scripts/export-memories.ts scripts/import-memories.ts
```

If missing, recreate wrappers or use plugin scripts directly:
```bash
npx tsx ~/.claude/plugins/marketplaces/thedotmack/scripts/export-memories.ts
```

### Logger initialization errors

Non-fatal warnings from plugin script. Usage message will still display correctly.

## Session Context

Created: January 3, 2026 (Session 229)
Reason: User questioned where export/import scripts were located
