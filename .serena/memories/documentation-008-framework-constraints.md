# Skill-Documentation-008: Framework Constraints

**Statement:** Add "Framework Limitations" section to SKILL.md documenting what Claude Code cannot do automatically

**Context:** When creating or updating .claude/skills/*/SKILL.md files

**Evidence:** Session 92: adr-review skill claimed automatic trigger but required manual BLOCKING gate enforcement

**Why:** Skills are pull-based (require explicit invocation), not push-based (automatic based on context). Aspirational documentation creates false expectations.

**Impact:** 7/10 - Prevents incorrect assumptions about skill activation

**Atomicity:** 88%

## Template

Every SKILL.md should include:

```markdown
## Framework Limitations

**What This Skill CANNOT Do:**

- ❌ Trigger automatically based on file creation (Claude Code has no file watchers)
- ❌ Trigger automatically based on tool output parsing (no event system)
- ❌ Run in background or parallel with other agents (sequential execution only)

**What Activation REQUIRES:**

- ✅ Explicit Skill() invocation by user or orchestrator
- ✅ BLOCKING gate enforcement in agent prompts (if mandatory)
- ✅ Detection pattern in orchestrator routing logic (if context-dependent)

**Current Enforcement:**

[Describe how this skill is actually invoked - user command, orchestrator routing, etc.]
```

## Example: adr-review Skill

**Aspirational (INCORRECT):**
"Triggers when architect creates ADR"

**Accurate (CORRECT):**
"Activated via BLOCKING gate: architect signals orchestrator with MANDATORY routing, orchestrator invokes Skill(skill='adr-review')"

## Verification

After writing SKILL.md:
- Does "Trigger" language match actual invocation mechanism?
- Is enforcement documented with detection patterns?
- Are framework limitations explicitly stated?

## Claude Code Framework Constraints (General)

| Capability | Supported? | Workaround |
|------------|------------|------------|
| File watchers | ❌ No | BLOCKING gates in agent prompts |
| Event-driven invocation | ❌ No | Detection patterns in orchestrator |
| Parallel skill execution | ❌ No | Sequential coordination via orchestrator |
| Automatic skill discovery | ❌ No | Explicit Skill() calls |
| Context-based triggering | ❌ No | Agent-to-orchestrator signaling |

## Related Skills

- protocol-blocking-gates: How to enforce mandatory skill invocation
- skill-orchestration-003-orchestrator-first-routing: Orchestrator routing patterns
