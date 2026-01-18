# Retrospective: Session Failures - 2025-12-17

## Summary

Comprehensive retrospective analysis of critical session failures. Two major incidents analyzed: (1) Failure to initialize Serena at session start, (2) Generation of auto-generated headers violating explicit user requirement.

## Incidents Analyzed

### Incident 1: Serena Initialization Failure

- **What happened**: Session started without calling `mcp__serena__initial_instructions` or `mcp__serena__activate_project`
- **Impact**: Blocked access to Serena memory and context tools throughout entire session
- **Root cause**: No mandatory session initialization protocol
- **User feedback**: "MANDATORY", "These should be called at the START of every session before any work"

### Incident 2: Auto-Generated Headers Violation

- **What happened**: Executed `Generate-Agents.ps1` without auditing, generated files with auto-generated headers
- **Impact**: Violated explicit user requirement, created reactive editing work
- **Root cause**: No script verification protocol, no user feedback retrieval
- **User feedback**: "The user had previously told me NOT to include auto-generated headers"

## Root Causes Identified

### Five Whys Results

1. **Serena Initialization**: Missing blocking protocol that enforces "initialize Serena BEFORE any other work"
2. **Auto-Generated Headers**: Missing verification protocol that checks script behavior against known user requirements

### Fishbone Analysis

Cross-category patterns identified:

- **Missing initialization protocol**: Appears in Sequence (wrong order), State (no tracking), Context (no retrieval)
- **No verification step**: Appears in Tools (no audit), Prompt (no feedback check), Sequence (wrong order)

### Force Field Analysis

- Forces balanced (16 driving vs 16 restraining)
- Conclusion: Need active intervention, not passive improvement
- Strategy: Create BLOCKING skills to shift force balance

## Skills Created

### Skill-Init-001: Session Initialization Protocol

- **Statement**: At session start, BEFORE any other action, call mcp__serena__initial_instructions and mcp__serena__activate_project
- **Atomicity**: 98%
- **Priority**: P0 - BLOCKING all other work
- **Memory location**: skill-init-001-session-initialization.md

### Skill-Verify-001: Script Audit Protocol

- **Statement**: Before executing any generation script, audit its code for alignment with known user requirements and identify dead/unused functions
- **Atomicity**: 95%
- **Priority**: P0 - BLOCKING script execution
- **Memory location**: skill-verify-001-script-audit.md

### Skill-Memory-001: User Feedback Retrieval

- **Statement**: Before executing scripts or making similar changes, search Serena memory for previous user feedback on that topic
- **Atomicity**: 93%
- **Priority**: P1 - BLOCKING similar actions
- **Memory location**: skill-memory-001-feedback-retrieval.md

### Skill-Audit-001: Dead Code Detection

- **Statement**: When reading utility scripts, identify functions that are defined but never called, and remove them before execution
- **Atomicity**: 94%
- **Priority**: P1 - Part of audit process
- **Memory location**: skill-audit-001-dead-code-detection.md

## Metrics

### Session Outcome

- **Success Rate**: 0% (multiple critical failures)
- **Mad (Blocked)**: 2 events
- **Sad (Suboptimal)**: 2 events  
- **Glad (Success)**: 0 events

### Learning Quality

- **Total learnings**: 4 skills
- **Average atomicity**: 95%
- **All learnings passed SMART validation**

### Retrospective Quality

- **ROTI Score**: 3 (High return)
- **Benefits**: Identified systemic process gaps, created 4 actionable skills
- **Time invested**: 30-40 minutes
- **Verdict**: Continue this retrospective pattern for critical failures

## Success Metrics for Future Sessions

### Observable Behaviors

1. **Serena initialized**: First tool calls are `mcp__serena__initial_instructions` and `mcp__serena__activate_project`
2. **Scripts audited**: Read script code before Bash execution
3. **Memory searched**: Memory search before similar actions
4. **Dead code removed**: Code changes show unused function removal

### Prevention Targets

- Zero sessions without Serena initialization
- Zero script executions without audit
- Zero repeat mistakes on user-stated preferences

## Dependencies Between Skills

- Skill-Init-001 BLOCKS all other work (must initialize first)
- Skill-Verify-001 DEPENDS ON Skill-Init-001 (needs Serena context)
- Skill-Memory-001 DEPENDS ON Skill-Init-001 (needs Serena memory)
- Skill-Audit-001 DEPENDS ON Skill-Verify-001 (part of audit process)

## Full Analysis

Complete retrospective document with all structured activities (4-Step Debrief, Execution Trace, Five Whys, Fishbone, Force Field, SMART validation) available at:
`.agents/retrospective/2025-12-17-session-failures.md`

## Tags

- #retrospective
- #critical-failure
- #session-2025-12-17
- #serena-initialization
- #script-audit
- #learnings
- #skills-created

## Related

- [retrospective-001-pr-learning-extraction](retrospective-001-pr-learning-extraction.md)
- [retrospective-001-recursive-extraction](retrospective-001-recursive-extraction.md)
- [retrospective-002-retrospective-to-skill-pipeline](retrospective-002-retrospective-to-skill-pipeline.md)
- [retrospective-003-token-impact-documentation](retrospective-003-token-impact-documentation.md)
- [retrospective-004-evidence-based-validation](retrospective-004-evidence-based-validation.md)
