# Spec-Generator Evaluation: Skill vs No Action

## Decision

**No Action Needed** (Outcome A)

The spec-generator agent already produces consistent EARS output when invoked. Format
inconsistency originates from manual spec creation that bypasses the agent entirely.

## Evidence

### Compliance Analysis (10 spec files)

| Metric | Count | Percentage |
|--------|-------|------------|
| EARS-compliant specs | 4 | 40% |
| Non-compliant specs | 6 | 60% |
| Duplicate IDs | 3 pairs | REQ-001, DESIGN-001, TASK-001 |

### Agent-Generated vs Manual Specs

| Origin | Files | EARS Compliant | Traceability |
|--------|-------|----------------|--------------|
| Agent-generated | REQ-001-pr-comment-handling, REQ-002-pr-comment-triage, DESIGN-001-pr-comment-processing, TASK-001/002/003-pr-* | Yes | Complete chain |
| Manual | REQ-001, REQ-a01, DESIGN-001, TASK-001 | No | Broken or missing |

### Evaluation Questions (from issue 617)

| Question | Finding | Implication |
|----------|---------|-------------|
| Are specs currently inconsistent? | Yes, 60% non-compliant | Problem exists |
| Is EARS format not being followed? | Only when agent is bypassed | Agent works correctly |
| Is traceability chain broken? | Yes, for manual specs only | Usage problem, not capability |
| Does spec-generator agent already produce consistent output? | Yes | No action needed on agent |

## Root Cause

The spec-generator agent prompt (`.claude/agents/spec-generator.md`) contains:

- Complete EARS templates (WHEN/THE SYSTEM SHALL/SO THAT)
- All five EARS patterns (Ubiquitous, Event-Driven, State-Driven, Optional, Unwanted)
- YAML frontmatter schemas with validation rules
- Traceability chain enforcement (REQ to DESIGN to TASK)
- Anti-pattern checklist

When invoked, the agent produces compliant output. The inconsistency comes from specs
created without the agent.

## Why a Skill Would Not Help

| Factor | Assessment |
|--------|------------|
| Agent output quality | Already deterministic and consistent |
| Skill duplication | Would replicate agent prompt content |
| Real gap | Usage enforcement, not format capability |
| Better fix | "Do Router" gate (ADR-033 Phase 4) to force spec-generator routing |

## Recommendation

1. **No skill creation**. The agent handles format consistency.
2. **Phase 4 consideration**: A future "Do Router" gate could enforce spec-generator
   routing when spec files are created. This belongs in ADR-033 Phase 4, not Phase 2.
3. **Cleanup**: Resolve duplicate IDs and convert manual specs to EARS format as
   separate maintenance work.

## References

- Issue: [#617](https://github.com/rjmurillo/ai-agents/issues/617)
- Parent: [#615](https://github.com/rjmurillo/ai-agents/issues/615)
- Agent prompt: `.claude/agents/spec-generator.md`
- Spec schemas: `.agents/governance/spec-schemas.md`
- ADR-033: `.agents/architecture/ADR-033-routing-level-enforcement-gates.md`
