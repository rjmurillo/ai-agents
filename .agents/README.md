# AI Agents Enhancement Project

> **Repository**: rjmurillo/ai-agents
> **Goal**: Reconcile Kiro planning patterns, Anthropic agent patterns, and existing implementation
> **Timeline**: 12-18 sessions across 6 phases

---

## Quick Start

1. Copy contents to your ai-agents repository's `.agents/` directory
2. Use `SESSION-START-PROMPT.md` to begin any session
3. Follow phase prompts in `PHASE-PROMPTS.md` for specific work
4. Use `SESSION-END-PROMPT.md` before ending any session

---

## File Inventory

| File | Purpose | Use When |
|------|---------|----------|
| **AGENT-INSTRUCTIONS.md** | Task execution protocol | Reference during all work |
| **SESSION-START-PROMPT.md** | Universal session initialization | Start of every session |
| **SESSION-END-PROMPT.md** | Universal session finalization | End of every session |
| **PHASE-PROMPTS.md** | Phase-specific orchestrator prompts | Starting each phase |
| **planning/enhancement-PROJECT-PLAN.md** | Master 6-phase project plan | Track progress |
| **prompts/GENERATE-AGENT-SYSTEM-PROMPT.md** | Generate AGENT-SYSTEM.md | One-time setup |

---

## Project Phases

| Phase | Name | Sessions | Key Deliverables |
|-------|------|----------|------------------|
| 0 | Foundation | 1-2 | Directory structure, governance docs |
| 1 | Spec Layer | 2-3 | EARS templates, spec-generator agent |
| 2 | Traceability | 2-3 | Validation scripts, pre-commit hooks |
| 3 | Parallel Execution | 2-3 | Fan-out documentation, aggregation |
| 4 | Steering Scoping | 2-3 | Glob-based steering, token tracking |
| 5 | Evaluator-Optimizer | 2-3 | Evaluation rubric, regeneration loop |
| 6 | Integration Testing | 1-2 | End-to-end test, retrospective |

---

## Installation

```bash
# In your ai-agents repository
mkdir -p .agents/planning .agents/prompts .agents/sessions .agents/governance .agents/specs .agents/steering

# Copy files
cp AGENT-INSTRUCTIONS.md .agents/
cp SESSION-START-PROMPT.md .agents/
cp SESSION-END-PROMPT.md .agents/
cp PHASE-PROMPTS.md .agents/
cp planning/enhancement-PROJECT-PLAN.md .agents/planning/
cp prompts/GENERATE-AGENT-SYSTEM-PROMPT.md .agents/prompts/

# Generate AGENT-SYSTEM.md using the prompt
# (delegate to explainer or architect agent)
```

---

## Key Concepts

### EARS Requirements Format

```text
WHEN [precondition/trigger]
THE SYSTEM SHALL [action/behavior]
SO THAT [rationale/value]
```

### 3-Tier Spec Hierarchy

```text
requirements.md (EARS format)
    ↓ traced by
design.md (architecture decisions)
    ↓ traced by
tasks.md (atomic work items)
```

### Evaluator-Optimizer Loop

```text
Generator → Evaluator (score) → Accept (≥70%) or Regenerate (<70%, max 3)
```

### Steering Injection

```text
*.cs files → load csharp-patterns.md steering
src/claude/*.md → load agent-prompts.md steering
```

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Traceability coverage | 100% |
| Token reduction (steering) | 30%+ |
| Evaluator quality improvement | +10% score |
| End-to-end test | Pass |

---

## Session Protocol Summary

**Start**:
1. Read context files (AGENT-SYSTEM, AGENT-INSTRUCTIONS, HANDOFF, PROJECT-PLAN)
2. Create session log
3. Identify current phase/task
4. Delegate to orchestrator

**Execute**:
1. Work incrementally
2. Commit frequently (conventional commits)
3. Update session log
4. Check off tasks

**End**:
1. Run retrospective agent
2. Update HANDOFF.md
3. Commit all documentation
4. Verify clean state
