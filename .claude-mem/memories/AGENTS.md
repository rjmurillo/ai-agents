# Claude-Mem Memory Import Agent Instructions

## Purpose

This directory contains Claude-Mem memory snapshots that should be imported at session start for team knowledge sharing and cross-session persistence.

## Session Start Import (REQUIRED)

Run the import script at session start:

```bash
pwsh scripts/Import-ClaudeMemMemories.ps1
```

The script is idempotent. Claude-Mem prevents duplicates using composite keys (`sdk_session_id` + `title` + `created_at_epoch`). Safe to run multiple times.

## Export at Session End

When ending sessions with valuable learnings:

```bash
npx tsx scripts/export-memories.ts "[query]" .claude-mem/memories/YYYY-MM-DD-session-NNN-topic.json
```

### Full Backup (Optional)

For milestone sessions or periodic backups:

```bash
pwsh .claude-mem/scripts/Export-ClaudeMemFullBackup.ps1
```

Exports ALL claude-mem data (observations, sessions, summaries, prompts) for institutional knowledge portability.

**Suggested**: Weekly or after major project milestones.

## Directory Contents

All `.json` files in this directory are memory exports that will be automatically imported.

## Naming Convention

`YYYY-MM-DD-session-NNN-topic.json`

Examples:

- `2026-01-03-session-229-frustrations.json`
- `2026-01-03-testing-philosophy.json`
- `2026-01-03-onboarding.json`

## Privacy Review

Before committing, review exports for:

- API keys, tokens, passwords
- Private file paths
- Confidential business logic
- Personal identifying information

## References

- [README.md](README.md) - Full documentation
- [ADR-007](../../.agents/architecture/ADR-007-memory-first-architecture.md) - Memory-First Architecture
