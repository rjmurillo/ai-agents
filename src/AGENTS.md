# Agent Source Directory

This directory contains agent definitions for all platforms.

## Style Guide

All agents MUST follow [STYLE-GUIDE.md](STYLE-GUIDE.md) for communication standards.

## Directory Contents

| Directory | Platform | File Pattern |
|-----------|----------|--------------|
| `claude/` | Claude Code CLI | `*.md` |
| `vs-code-agents/` | VS Code / GitHub Copilot | `*.agent.md` |
| `copilot-cli/` | GitHub Copilot CLI | `*.agent.md` |

## Canonical Instructions

Full agent documentation, workflows, and protocols: [../AGENTS.md](../AGENTS.md)

Cross-harness agent changes must use the contract in
`.claude/skills/agent-harness-reference/`. Execute hook or runtime-port changes
through `ai-agents-portability-campaign`, then regenerate this tree.
