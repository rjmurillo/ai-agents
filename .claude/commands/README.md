# Slash Command Catalog

Custom slash commands for Claude Code. All commands follow quality gates (frontmatter, security, validation).

## Memory Commands

| Command | Description | Arguments |
|---------|-------------|-----------|
| `/memory-list` | List recent Forgetful memories | `[project-name]` |
| `/memory-save` | Save current context to Forgetful | None |
| `/memory-search` | Semantic search across memories | `<search-query>` |
| `/memory-explore` | Deep knowledge graph exploration | `<starting-query>` |
| `/memory-documentary` | Generate evidence-based reports | None |

**Extended Thinking**: `memory-explore`, `memory-documentary`

## Research Commands

| Command | Description | Arguments |
|---------|-------------|-----------|
| `/research` | Research topics and incorporate into memory | `<topic-or-url>` |
| `/context_gather` | Gather context from multiple sources | `<task-or-technology>` |

**Extended Thinking**: `research`

## Workflow Commands

Numbered pipeline commands for structured agent orchestration (`/0-init → /1-plan → /2-impl → /3-qa → /4-security`).

| Command | Description | Arguments |
|---------|-------------|-----------|
| `/workflow/0-init` | Session initialization (ADR-007 memory-first) | `[--session-number N] [--objective "text"]` |
| `/workflow/1-plan` | Planning phase — routes to planner/architect/roadmap | `[--arch] [--strategic] <task>` |
| `/workflow/2-impl` | Implementation — default/full/parallel modes | `[--full] [--parallel] <task>` |
| `/workflow/3-qa` | Quality assurance — coverage + acceptance criteria | `[--coverage-threshold N] <scope>` |
| `/workflow/4-security` | Security review (opus) — OWASP + secrets + deps | `[--owasp-only] [--secrets-only] <scope>` |

See [docs/workflow-commands.md](../../docs/workflow-commands.md) for complete documentation.

## Development Commands

| Command | Description | Arguments |
|---------|-------------|-----------|
| `/pr-review` | Respond to PR review comments | `[pr-number]` |
| `/push-pr` | Commit, push, and create PR | None |
| `/context-hub-setup` | Configure Context Hub dependencies | None |

**Extended Thinking**: `pr-review`

## Usage Examples

```bash
# Search memories
/memory-search "PowerShell array handling"

# Research with extended thinking
/research "Roslyn analyzer best practices"

# PR review with deep analysis
/pr-review 123
```

## Creating New Commands

Use the SlashCommandCreator skill:

```text
SlashCommandCreator: create command for [purpose]
```

Or manually:

```bash
pwsh .claude/skills/slashcommandcreator/scripts/New-SlashCommand.ps1 -Name "my-command"
```

## Validation

All commands pass quality gates:

```bash
pwsh .claude/skills/slashcommandcreator/scripts/Validate-SlashCommand.ps1 -Path .claude/commands/[name].md
```

**Pre-commit hook**: Automatically validates staged commands
**CI/CD**: GitHub Actions workflow validates on PR

## Documentation

For detailed usage guidelines, see [CLAUDE.md](../../CLAUDE.md#custom-slash-commands).
