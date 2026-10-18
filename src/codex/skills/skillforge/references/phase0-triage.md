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

### How Matches Are Scored

- Request scaffolding words ("create", "skill", "with", "for", and similar) are dropped before scoring. They describe the request, not its subject.
- Domain terms match on whole words. "test" matches "testing" and "tests", never "attest". "ci" never matches inside "social". Skill names and triggers follow the same rule, with hyphens read as spaces in both the skill text and the query, so the trigger `code-review` matches "do a code review". A skill name or trigger made only of scaffolding words (a skill named `build` or `make`) never matches: "build a skill for X" frames the request.
- A skill's score is discounted by coverage, the fraction of the remaining query terms that the skill name, keywords, triggers, description, or declared domain synonyms explain. The discount is half strength: a skill that explains none of the terms keeps half its score. A request of three or more terms that rests on one explained term is capped at 49, so one shared word cannot reach the 50% boundary. A query that names the skill exactly is exempt.
- Input that fits no other category and still carries three or more content terms routes to CREATE_NEW when no skill scores 50 or higher. Shorter unclear input, or a 50-69 match, routes to CLARIFY.
- `discover_skills.py` assigns domains from the skill name, description, and extracted keywords. It does not scan the SKILL.md body. Rebuild the index after upgrading so older domain assignments are replaced.

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
