# Overview and Triggers

## Quick Start

**Any input works.** SkillForge will intelligently route to the right action:

```
# These all work - SkillForge figures out what you need:

SkillForge: create a skill for automated code review
→ Creates new skill (after checking no duplicates exist)

help me debug this TypeError
→ Recommends ErrorExplainer skill (existing)

improve the testgen skill to handle React components better
→ Enters improvement mode for TestGen

do I have a skill for database migrations?
→ Recommends DBSchema, database-migration skills

TypeError: Cannot read property 'map' of undefined
→ Routes to debugging skills (error detected)
```

---

## Triggers

### Creation Triggers

- `SkillForge: {goal}` - Full autonomous skill creation
- `create skill` - Natural language activation
- `design skill for {purpose}` - Purpose-first creation
- `ultimate skill` - Emphasize maximum quality
- `SkillForge --plan-only` - Generate specification without execution

### Routing Triggers (NEW in v4.0)

- `{any input}` - Analyzes and routes automatically
- `do I have a skill for` - Searches existing skills
- `which skill` / `what skill` - Recommends matching skills
- `improve {skill-name} skill` - Enters improvement mode
- `help me with` / `I need to` - Detects task and routes

| Input | Output | Quality Gate |
|-------|--------|--------------|
| Any input | Triage → Route → Action | Phase 0 analysis |
| Explicit create | New skill | Unanimous panel approval |
| Skill question | Skill recommendation | Match confidence ≥60% |
| Task / code / URL | Recommend, improve, or compose | ≥80% recommend; 50-79% improve |

---

## Process Overview

```
ANY USER INPUT
(prompt, error, code, URL, question, task request)
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ Phase 0: SKILL TRIAGE (NEW)                         │
│ • Classify input type (create/improve/question/task)│
│ • Scan 250+ skills in ecosystem                     │
│ • Match against existing skills with confidence %   │
│ • Route to: USE | IMPROVE | CREATE | COMPOSE        │
├─────────────────────────────────────────────────────┤
│         ↓ USE_EXISTING    ↓ IMPROVE      ↓ CREATE   │
│      [Recommend]      [Load & Enhance] [Continue]   │
└─────────────────────────────────────────────────────┘
    │ (if CREATE_NEW or IMPROVE_EXISTING)
    ▼
┌─────────────────────────────────────────────────────┐
│ Phase 1: DEEP ANALYSIS                              │
│ • Expand requirements (explicit, implicit, unknown) │
│ • Apply 11 thinking models + Automation Lens        │
│ • Question until no new insights (3 empty rounds)   │
│ • Identify automation/script opportunities          │
├─────────────────────────────────────────────────────┤
│ Phase 2: SPECIFICATION                              │
│ • Generate XML spec with all decisions + WHY        │
│ • Include scripts section (if applicable)           │
│ • Validate timelessness score ≥ 7                   │
├─────────────────────────────────────────────────────┤
│ Phase 3: GENERATION                                 │
│ • Write SKILL.md with fresh context                 │
│ • Generate references/, assets/, and scripts/       │
├─────────────────────────────────────────────────────┤
│ Phase 4: SYNTHESIS PANEL                            │
│ • 3-4 Opus agents review independently              │
│ • Script Agent added when scripts present           │
│ • All agents must approve (unanimous)               │
│ • If rejected → loop back with feedback             │
└─────────────────────────────────────────────────────┘
    │
    ▼
Production-Ready Agentic Skill
```

**Key principles:**

- **Phase 0 prevents duplicates** - Always checks existing skills first
- Evolution/timelessness is the core lens (score ≥ 7 required)
- Every decision includes WHY
- Zero tolerance for errors
- Autonomous execution at maximum depth
- Scripts enable self-verification and agentic operation

### Tool Escalation Policy

Start with least privilege (`Read`, `Glob`, `Grep`, `Write`, `Edit`).

Only add higher-risk tools when explicitly required:

- `Bash` for deterministic local scripts that cannot be replaced with file edits
- `WebFetch` / `WebSearch` only when external facts are required
- `Task` only for true parallel sub-agent orchestration

---

## Commands

| Command | Action |
|---------|--------|
| `SkillForge: {goal}` | Full autonomous execution |
| `SkillForge --plan-only {goal}` | Generate specification only |
| `SkillForge --quick {goal}` | Reduced depth (not recommended) |
| `SkillForge --triage {input}` | Run Phase 0 triage only |
| `SkillForge --improve {skill}` | Enter improvement mode for existing skill |

---
