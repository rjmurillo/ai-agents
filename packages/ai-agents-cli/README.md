# @rjmurillo/ai-agents

Vendor the ai-agents Claude kit into any repository.

## Usage

```bash
npx @rjmurillo/ai-agents init
```

`init` copies the kit's agents, skills, and rules into `.claude/` of the current
directory, merges an ai-agents block into CLAUDE.md (or
`.github/copilot-instructions.md` with `--target copilot` or `both`), creates
AGENTS.md if missing, and writes a version pin at `.claude/.ai-agents-version.json`.
Use `--dry-run` to see every write first.

Run `npx @rjmurillo/ai-agents --help` for all options. The
[installation guide](https://github.com/rjmurillo/ai-agents/blob/main/docs/installation.md)
covers `--target`, `--pack`, and `--force`.

Requires Node 20 or later.

## Source

<https://github.com/rjmurillo/ai-agents>
