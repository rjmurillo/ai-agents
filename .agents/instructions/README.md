# Path-Scoped Instructions

> **Status**: Operational Rules (Complements Steering)
> **Last Updated**: 2026-04-21
> **RFC 2119**: This directory uses RFC 2119 key words.

## Purpose

Path-scoped instructions are short, operational rules that load only when an agent edits files matching a glob pattern. They consolidate path-specific governance, approval, and workflow requirements that were previously scattered across ADRs, governance docs, and tribal knowledge.

## Scope Boundary

This directory is distinct from two related locations:

| Location | Role | Content |
|----------|------|---------|
| `.agents/steering/` | Canonical reference | Code patterns, conventions, standards |
| `.agents/instructions/` | Path-scoped operational rules | Approval gates, downstream effects, required follow-ups |
| `.github/instructions/` | Copilot CLI entry points | Lightweight pointers with `applyTo` for Copilot |

When an agent edits a file, it reads `.agents/instructions/*.instructions.md` whose `applyTo` glob matches the file. Steering explains *how to write* code for a domain; instructions explain *what rules apply* when touching a path.

## File Format

Every instruction file MUST have YAML frontmatter with an `applyTo` field:

```yaml
---
applyTo: "<glob pattern or comma-separated list>"
priority: <optional: critical | high | normal>
---
```

Content SHOULD be terse (< 60 lines), cite authoritative sources for detail, and avoid duplicating steering content.

## Loading Mechanism

| Harness | Mechanism |
|---------|-----------|
| Copilot CLI | Mirror files in `.github/instructions/` — Copilot auto-loads by `applyTo` |
| Claude Code | `CLAUDE.md` directs agent to read matching `.agents/instructions/*.instructions.md` before editing |
| Cortex / Factory Droid / DevClaw | Worker prompt reads matching files from this directory |

## Files

| File | `applyTo` | Purpose |
|------|-----------|---------|
| [universal.instructions.md](universal.instructions.md) | `**` | Rules that apply to every change |
| [governance.instructions.md](governance.instructions.md) | `.agents/governance/**` | Human approval + consensus required |
| [security.instructions.md](security.instructions.md) | `.agents/security/**` | Always-on review, evidence required |
| [templates.instructions.md](templates.instructions.md) | `templates/**` | Source of truth, regenerate downstream |
| [ci-scripts.instructions.md](ci-scripts.instructions.md) | `scripts/**`, `.github/workflows/**` | CI-critical, test before commit |
| [testing.instructions.md](testing.instructions.md) | `tests/**`, `**/*.Tests.ps1` | Pester + pytest conventions (ADR-023) |
| [retros.instructions.md](retros.instructions.md) | `.agents/retrospective/**` | Retrospective format and classification |
| [claude-agents.instructions.md](claude-agents.instructions.md) | `src/claude/**`, `.claude/agents/**`, `.claude/skills/**` | Template sync, generator runs |

## Authoring Rules

1. Rules MUST be stated with RFC 2119 key words (MUST, SHOULD, MAY).
2. Each rule SHOULD cite an ADR, governance doc, or retrospective.
3. Files SHOULD NOT duplicate `.agents/steering/` content; link instead.
4. Glob patterns MUST be comma-separated strings (no YAML lists) for Copilot compatibility.
5. Changes to this directory follow `.agents/governance/` rules (see `governance.instructions.md`).

## References

- `.agents/steering/README.md` — steering architecture
- `.agents/governance/PROJECT-CONSTRAINTS.md` — canonical constraints
- `.agents/SESSION-PROTOCOL.md` — session gates
- Issue #1727 — introduction of this directory
- Retrospective `2025-12-15-instruction-files-gap.md` — motivating failure mode
