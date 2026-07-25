# Harness-Agnostic Hook Contract

This directory preserves the original Phase 1 contract from issue #1726. It is
not the runtime source of truth.

## Current Sources of Truth

| Surface | Role |
|---|---|
| `.claude/settings.json` | Claude Code repository registrations |
| `.claude/hooks/dispatch_groups.json` | Claude grouped-dispatch membership |
| `.claude/hooks/` | Canonical hook scripts |
| `templates/platforms/copilot-cli.yaml` | Copilot event mapping and generation policy |
| `build/scripts/generate_hooks.py` | Copilot hook generator entrypoint |
| `src/copilot-cli/hooks/hooks.json` | Generated Copilot registrations |
| `src/copilot-cli/hooks/` | Generated Copilot scripts and dispatchers |
| `.claude/skills/agent-harness-reference/` | Official contracts, citations, and versioned probes |

`.agents/hooks/hooks.yaml` is a retired inventory. No generator or runtime reads
it. Do not add registrations there. Edit the Claude source, update the Copilot
platform policy when needed, then regenerate.

## Current Event Mapping

| Claude source | Copilot target | Generated policy |
|---|---|---|
| `PreToolUse` | `PreToolUse` | One fail-closed gate dispatcher |
| `PostToolUse` | `PostToolUse` | One observer dispatcher; text merges into `additionalContext` |
| `SessionStart` | `SessionStart` | One observer dispatcher; repository prose is discarded |
| `PreCompact` | `PreCompact` | One observer dispatcher; checkpoint prose is discarded |
| `UserPromptSubmit` | `UserPromptSubmit` | One observer dispatcher; text goes to stderr |
| `Stop` | `Stop` | Direct host registrations; structured decisions stay separate |

`PermissionRequest` has a tested translation path but no registered producer.
`PostToolUseFailure` stays direct because exit-2 stdout becomes recovery
context. Any unclassified future event stays direct until its output and
failure contracts are reviewed. `Stop` is per-turn completion. It is not
`SessionEnd`.

## Output and Failure Rules

- Claude Code and Copilot CLI do not share one universal exit-code contract.
  Apply event-specific rules from `agent-harness-reference`.
- Copilot parses at most one final JSON document per command hook. Merge only
  fields with an event-specific policy and positive, negative, and edge tests.
- Both grouped dispatchers capture Python stdout, direct writes to file
  descriptor 1, and inherited child-process stdout.
- Copilot discards SessionStart and PreCompact prose. Direct rollback commands
  preserve producer side effects while suppressing stdout and stderr.
- Copilot timeouts fail open on the measured 1.0.72-1 host. Later guards may
  not run after a dispatcher timeout.
- Copilot matcher support is version-sensitive. Generated matcher shims remain
  the final in-process filter.

## Generation

After changing canonical hooks or registration policy:

```bash
uv run python build/scripts/build_all.py
uv run python build/scripts/build_all.py --check
```

Commit canonical edits and generated outputs together. The generation and
release runbook is `.claude/skills/ai-agents-generation-and-release/SKILL.md`.

## Historical Artifacts

The `examples/` directory and retired `hooks.yaml` record issue #1726's Phase 1
shape. They are not installable hook surfaces. The post-eval script is also not
a harness lifecycle hook. The eval pipeline invokes it after a benchmark run.
