---
name: skillcreator
description: "Ultimate meta-skill for creating production-ready Claude Code skills. Uses deep iterative analysis with 11 thinking models, regression questioning until exhausted, evolution and timelessness as core lens, and multi-agent synthesis panel for unanimous approval. Includes automation analysis for agentic scripts. Fully autonomous execution at maximum depth produces categorically the best possible skills."
license: MIT
metadata:
  version: 3.2.0
  model: claude-opus-4-5-20251101
  subagent_model: claude-opus-4-5-20251101
  domains: [meta-skill, automation, skill-creation, orchestration, agentic]
  type: orchestrator
  inputs: [user-goal, domain-hints]
  outputs: [SKILL.md, references/, scripts/, SKILL_SPEC.md]
---

# SkillCreator 3.2 - Ultimate Meta-Skill

Create categorically the best possible Claude Code skills.

## Quick Start

Just tell me what skill you need:

```text
SkillCreator: create a skill for automated code review
```

That's it. The skill will be created autonomously with full analysis, verification, and quality gates.

## Triggers

- `SkillCreator: {goal}` - Full autonomous skill creation
- `create skill` - Natural language activation
- `design skill for {purpose}` - Purpose-first creation
- `ultimate skill` - Emphasize maximum quality
- `skillcreator --plan-only` - Generate specification without execution
- `SkillCreator --quick {goal}` - Reduced depth (not recommended)

| Input | Output | Quality Gate |
|-------|--------|--------------|
| Your goal | Production-ready skill | Unanimous 3/3 panel approval |

## Process Overview

```text
Your Request
    │
    ▼
Phase 1: DEEP ANALYSIS
  • Expand requirements (explicit, implicit, unknown)
  • Apply 11 thinking models + Automation Lens
  • Question until no new insights (3 empty rounds)
    │
    ▼
Phase 2: SPECIFICATION
  • Generate XML spec with all decisions + WHY
  • Validate timelessness score ≥ 7
    │
    ▼
Phase 3: GENERATION
  • Write SKILL.md with fresh context
  • Generate references/, assets/, and scripts/
    │
    ▼
Phase 4: SYNTHESIS PANEL
  • 3-4 Opus agents review independently
  • All agents must approve (unanimous)
    │
    ▼
Production-Ready Skill
```

**Key principles:**

- Evolution/timelessness is the core lens (score ≥ 7 required)
- Every decision includes WHY
- Zero tolerance for errors
- Autonomous execution at maximum depth

## Commands

| Command | Action |
|---------|--------|
| `SkillCreator: {goal}` | Full autonomous execution |
| `SkillCreator --plan-only {goal}` | Generate specification only |

## Validation & Packaging

Before distribution, validate your skill:

```bash
# Quick validation (required for packaging)
python scripts/quick_validate.py ~/.claude/skills/my-skill/

# Full structural validation
python scripts/validate-skill.py ~/.claude/skills/my-skill/

# Package for distribution
python scripts/package_skill.py ~/.claude/skills/my-skill/ ./dist
```

## On Invocation

**REQUIRED**: Read these references before proceeding:

1. `Read references/phases.md` - Detailed phase workflows
2. `Read references/multi-lens-framework.md` - 11 thinking models
3. `Read references/regression-questions.md` - Question bank

For scripts: `Read references/script-integration-framework.md`

## Skill Output Structure

```text
~/.claude/skills/{skill-name}/
├── SKILL.md                    # Main entry point (required)
├── references/                 # Deep documentation (optional)
├── assets/                     # Templates (optional)
└── scripts/                    # Automation scripts (optional)
```

### Scripts Directory

Scripts enable skills to be **agentic**, capable of autonomous operation with self-verification.

| Category | Purpose | When to Include |
|----------|---------|-----------------|
| **Validation** | Verify outputs meet standards | Skill produces artifacts |
| **Generation** | Create artifacts from templates | Repeatable artifact creation |
| **State Management** | Track progress across sessions | Long-running operations |
| **Transformation** | Convert/process data | Data processing tasks |
| **Calculation** | Compute metrics/scores | Scoring or analysis |

**Script Requirements:**

- Python 3.x with standard library only (graceful fallbacks for extras)
- `Result` dataclass pattern for structured returns
- Exit codes: 0=success, 1=failure, 10=validation failure, 11=verification failure
- Self-verification where applicable
- Documented in SKILL.md with usage examples

See: [references/script-integration-framework.md](references/script-integration-framework.md)

## Frontmatter Requirements

| Property | Required | Description |
|----------|----------|-------------|
| `name` | Yes | Hyphen-case, max 64 chars |
| `description` | Yes | Max 1024 chars, no angle brackets |
| `license` | No | MIT, Apache-2.0, etc. |
| `metadata` | No | Custom fields (version, model, etc.) |

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Duplicate skills | Bloats registry | Check existing first |
| Single trigger | Hard to discover | 3-5 varied phrases |
| No verification | Can't confirm success | Measurable outcomes |
| Over-engineering | Complexity without value | Start simple |
| Missing WHY | Can't evolve | Document rationale |

## Verification Checklist

After creation:

- [ ] Frontmatter valid (only allowed properties)
- [ ] Name is hyphen-case, ≤64 chars
- [ ] Description ≤1024 chars, no `<` or `>`
- [ ] 3-5 trigger phrases defined
- [ ] Timelessness score ≥ 7
- [ ] `python scripts/quick_validate.py` passes

## References

Load these on invocation for detailed guidance:

- [phases.md](references/phases.md) - Complete phase workflows
- [regression-questions.md](references/regression-questions.md) - Question bank (7 categories)
- [multi-lens-framework.md](references/multi-lens-framework.md) - 11 thinking models
- [specification-template.md](references/specification-template.md) - XML spec structure
- [evolution-scoring.md](references/evolution-scoring.md) - Timelessness evaluation
- [synthesis-protocol.md](references/synthesis-protocol.md) - Multi-agent panel details
- [script-integration-framework.md](references/script-integration-framework.md) - Script patterns

## Related Skills

| Skill | Relationship |
|-------|--------------|
| skill-composer | Can orchestrate created skills |
| claude-authoring-guide | Deeper patterns reference |
| codereview | Pattern for multi-agent panels |
| maker-framework | Zero error standard source |

## Extension Points

1. **Additional Lenses:** Add thinking models to `references/multi-lens-framework.md`
2. **New Synthesis Agents:** Extend panel for specific domains
3. **Script Patterns:** Add patterns to `references/script-patterns-catalog.md`

## Changelog

### v3.2.0 (Current)

- Added Script Integration Framework for agentic skills
- Added 4th Script Agent to synthesis panel (conditional)
- Added Phase 1D: Automation Analysis
- Skills can now include self-verifying Python scripts

### v3.1.0

- Added progressive disclosure structure
- Fixed frontmatter for packaging compatibility

### v3.0.0

- Complete redesign as ultimate meta-skill
- Added regression questioning loop
- Added multi-lens analysis framework (11 models)
- Added evolution/timelessness core lens
- Added multi-agent synthesis panel
