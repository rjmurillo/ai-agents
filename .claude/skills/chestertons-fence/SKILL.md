---
name: chestertons-fence
version: 1.0.0
model: claude-sonnet-4-5
description: Investigate historical context of existing code, patterns, or constraints before proposing changes. Automates git archaeology, PR/ADR search, and dependency analysis to prevent removing structures without understanding their purpose.
license: MIT
---

# Chesterton's Fence Investigation

Enforce epistemic humility before changing existing systems. Requires understanding original purpose before proposing changes.

## Triggers

| Phrase | Context |
|--------|---------|
| `why does this exist` | Investigating existing code or patterns |
| `chestertons fence` | Explicit investigation request |
| `before removing` | Planning deletion or replacement |
| `historical context` | Researching original rationale |
| `prior art investigation` | ADR-required investigation |

## Quick Reference

| Input | Output | Destination |
|-------|--------|-------------|
| File path or ADR number | Investigation report | `.agents/analysis/NNN-chestertons-fence-TOPIC.md` |
| Component description | Historical context summary | stdout (JSON) |

## When to Use

Use this skill BEFORE proposing changes to existing:

- Code patterns or architectural decisions
- ADRs, constraints, or protocol rules
- Workflow configurations or CI pipelines
- Skills, hooks, or agent prompts

## Process

```text
1. Identify Structure    What exists? Where?
       |
       v
2. Git Archaeology       git log/blame to find origin
       |
       v
3. PR/ADR Search         Find original rationale
       |
       v
4. Dependency Analysis   What references this?
       |
       v
5. Generate Report       Fill investigation template
       |
       v
6. Decision              REMOVE / MODIFY / PRESERVE / REPLACE
```

## Usage

```bash
# Investigate a file or pattern
python3 scripts/investigate.py --target path/to/file.py --change "remove unused validation"

# Investigate an ADR
python3 scripts/investigate.py --target .agents/architecture/ADR-005.md --change "allow bash scripts"

# Output as JSON (for automation)
python3 scripts/investigate.py --target path/to/file.py --change "description" --format json
```

## Integration with Agent Workflows

### Analyst Agent

When investigating changes to existing systems, run this skill first. The investigation report becomes a prerequisite for any change proposal.

### Architect Agent

ADRs that deprecate or replace existing patterns MUST include a "Prior Art Investigation" section. Use this skill to generate it.

### Implementer Agent

Before implementing deletions or major refactoring, verify that an investigation report exists. If missing, route to analyst.

### Critic Agent

When validating plans that remove or replace existing systems, check for investigation evidence. Auto-reject proposals without historical context.

## Template

Investigation reports use the template at `.agents/templates/chestertons-fence-investigation.md`.
