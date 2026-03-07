# Project Structure

This page explains the high-level layout of `rjmurillo/ai-agents` and (most importantly) what files you should edit vs avoid.

## Quick orientation

- If you want to change an agent’s behavior, you usually edit **templates**, then regenerate outputs.
- If you want to *use* agents in a repo, look at **.github/agents/** (Copilot/VS Code) and **.claude/agents/** (Claude Code).
- If you want to understand the overall system, start with **README.md** and **AGENTS.md**.

## Top-level layout (annotated)

```text
ai-agents/
├── README.md                 # Project overview + install + examples
├── AGENTS.md                 # Canonical usage guide + session protocol
├── CONTRIBUTING.md           # How to contribute (prereqs, tests, regeneration)
├── CLAUDE.md                 # Claude Code integration instructions
├── CRITICAL-CONTEXT.md       # Blocking constraints for agent sessions
├── LICENSE
│
├── docs/                     # Human documentation (this folder)
│   ├── installation.md       # How to install agents via skill-installer
│   ├── ideation-workflow.md  # "shower thought" → PRD/plan workflow
│   ├── autonomous-*.md       # Autonomous workflows (PR monitor, issue dev)
│   └── project-structure.md  # (this file)
│
├── templates/                # SOURCE OF TRUTH for most agent content
│   ├── agents/               # `*.shared.md` agent templates (edit these)
│   └── platforms/            # Platform-specific generation config (YAML)
│
├── build/                    # Build + generation scripts
│   └── Generate-Agents.ps1   # Regenerates platform agent files from templates
│
├── src/                      # GENERATED agent files for distribution
│   ├── vs-code-agents/       # Generated VS Code prompt/agent files (don’t edit)
│   ├── copilot-cli/          # Generated Copilot CLI agent files (don’t edit)
│   └── claude/               # Claude Code agent files + skills (some generated)
│
├── .github/                  # GitHub automation + Copilot integration
│   ├── agents/               # Copilot/VS Code agents used by GitHub tooling
│   ├── prompts/              # Prompts used by workflows (quality gates, triage)
│   └── workflows/            # CI workflows (keep logic in scripts, not YAML)
│
├── .claude/                  # Claude Code local integration
│   ├── agents/               # Claude Code agents for this repo
│   ├── skills/               # Claude Code skills used by the system
│   └── hooks/                # Hook dependencies + optional automation
│
├── scripts/                  # Shared scripts used by workflows and local tooling
├── tests/                    # pytest tests (Python)
└── test/                     # Additional test assets / harness
```

## What you should edit (common tasks)

### Modify an agent

Edit the shared template:

- `templates/agents/<agent>.shared.md`

Then regenerate:

```powershell
pwsh build/Generate-Agents.ps1
```

Commit both the template and the generated outputs.

### Add documentation

Add docs under:

- `docs/`

And link them from **README.md** (keep the root README focused on getting started).

### Contribute code / scripts

- Python dependencies and packaging: `pyproject.toml`
- Shared automation scripts: `scripts/`
- Tests: `tests/`

## What you should generally NOT edit

- `src/vs-code-agents/` and `src/copilot-cli/` are generated outputs.
- `.agents/HANDOFF.md` is explicitly **read-only** (a dashboard, not a working file).

## “Where do artifacts go?”

This repo uses two main artifact locations:

- `.agents/` for plans, ADRs, reviews, session logs, and workflow artifacts.
- `.serena/` for curated, reusable “memories” and project metadata.

If you are building new automation, prefer writing artifacts to these folders so the rest of the system can discover them.
