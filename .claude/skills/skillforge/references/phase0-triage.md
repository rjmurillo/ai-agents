# Phase 0 Skill Triage

## Phase 0: Skill Triage (NEW in v4.0)

Before creating anything, SkillForge intelligently analyzes your input to determine the best action.

### How It Works

```
┌────────────────────────────────────────────────────────────────────┐
│                        ANY USER INPUT                               │
│  (prompt, error, code, URL, question, task request, anything)      │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  Step 1: INPUT CLASSIFICATION                                       │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐       │
│  │ explicit_create │ │ explicit_improve│ │ skill_question  │       │
│  │ "create skill"  │ │ "improve skill" │ │ "do I have..."  │       │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘       │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐       │
│  │  task_request   │ │  error_message  │ │  code_snippet   │       │
│  │ "help me with"  │ │ "TypeError..."  │ │ [pasted code]   │       │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘       │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  Step 2: SKILL ECOSYSTEM SCAN                                       │
│  • Load index of 250+ skills (discover_skills.py)                  │
│  • Match input against all skills with confidence scoring          │
│  • Identify top matches with reasons                               │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  Step 3: DECISION MATRIX                                            │
│                                                                     │
│  Match ≥80%  + explicit create → CLARIFY (duplicate warning)       │
│  Match ≥60%  + skill question  → USE_EXISTING (recommend skill)    │
│  Match ≥80%  + other input     → USE_EXISTING (recommend skill)    │
│  Match 50-79%                  → IMPROVE_EXISTING (enhance match)  │
│  Match <50%  + explicit create → CREATE_NEW (proceed to Phase 1)   │
│  Multi-domain detected         → COMPOSE (suggest skill chain)     │
│  Ambiguous input               → CLARIFY (ask for more info)       │
└────────────────────────────────────────────────────────────────────┘
```

### Decision Actions

| Action | When | Result |
|--------|------|--------|
| **USE_EXISTING** | Match ≥80% (task, code, URL) or ≥60% (skill question) | Recommends existing skill(s) to invoke |
| **IMPROVE_EXISTING** | Match 50-79% | Loads skill and enters enhancement mode |
| **CREATE_NEW** | Match <50% | Proceeds to Phase 1 (Deep Analysis) |
| **COMPOSE** | Multi-domain | Suggests skill chain via SkillComposer |
| **CLARIFY** | Ambiguous or duplicate | Asks user to clarify intent |

### Triage Script

```bash
# Run triage on any input
python scripts/triage_skill_request.py "help me debug this error"

# JSON output for automation
python scripts/triage_skill_request.py "create a skill for payments" --json

# Examples:
python scripts/triage_skill_request.py "TypeError: Cannot read property 'map'"
# → USE_EXISTING: Recommends ErrorExplainer (92%)

python scripts/triage_skill_request.py "create a skill for code review"
# → CLARIFY: CodeReview skill exists (85%), create anyway?

python scripts/triage_skill_request.py "help me with API and auth and testing"
# → COMPOSE: Multi-domain, suggests APIDesign + AuthSystem + TestGen chain
```

### Ecosystem Index

Phase 0 uses a pre-built index of all skills:

```bash
# Rebuild skill index (run periodically or after installing new skills)
python scripts/discover_skills.py

# Index location: ~/.cache/skillrecommender/skill_index.json
# Scans: ~/.claude/skills/, plugins/marketplaces/*, plugins/cache/*
```

### Integration with Phases 1-4

- **USE_EXISTING**: Exits early, no creation needed
- **IMPROVE_EXISTING**: Loads existing skill → Phase 1 analyzes gaps → Phase 2-4 enhance
- **CREATE_NEW**: Full pipeline (Phase 1 → 2 → 3 → 4)
- **COMPOSE**: Suggests using SkillComposer instead
- **CLARIFY**: Pauses for user input before proceeding

---
