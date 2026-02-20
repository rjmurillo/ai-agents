# Evaluation: spec-generator Skill vs No Action

Issue: #617
Date: 2026-02-20
Decision: **No Action Needed** (Outcome A)

## Investigation Summary

Evaluated whether spec-generator needs a dedicated skill for EARS format standardization.

## Evidence

### Spec Files Analyzed

| File | Author | EARS Compliant | Traceability |
|------|--------|---------------|--------------|
| REQ-001-pr-comment-handling.md | spec-generator | Yes | REQ-001 to DESIGN-001 |
| REQ-002-pr-comment-triage.md | spec-generator | Yes | REQ-002 to DESIGN-001 |
| DESIGN-001-pr-comment-processing.md | spec-generator | N/A (design tier) | DESIGN-001 to TASK-001/002/003 |
| TASK-001-pr-context-scripts.md | spec-generator | N/A (task tier) | TASK-001 to DESIGN-001 |
| REQ-001.md | (unknown) | No | Partial (links exist, no EARS) |
| REQ-a01-factory-mcp-config-generation.md | factory-droid[bot] | No | None (no DESIGN/TASK links) |

### Key Findings

1. **spec-generator output is consistent.** All specs authored by spec-generator use EARS syntax ("WHEN... THE SYSTEM SHALL... SO THAT") with proper YAML frontmatter.
2. **Traceability chains are intact.** spec-generator specs maintain complete REQ to DESIGN to TASK chains with bidirectional links.
3. **Inconsistencies come from other sources.** Non-EARS specs (REQ-001.md, REQ-a01) were authored by other agents or manual processes, not spec-generator.
4. **Agent prompt is comprehensive.** `src/claude/spec-generator.md` already includes EARS templates, validation checklists, traceability rules, and anti-pattern guidance (446 lines).

### Evaluation Matrix (from Issue)

| Question | Answer | Result |
|----------|--------|--------|
| Are specs currently inconsistent? | Only non-spec-generator specs | No action for spec-generator |
| Is EARS format not being followed? | Followed by spec-generator, not by others | No action for spec-generator |
| Is traceability chain broken? | Intact in spec-generator output | No action |
| Does spec-generator already produce consistent output? | Yes | No action |

## Decision Rationale

The spec-generator agent already produces consistent, EARS-compliant specifications with complete traceability. The existing agent prompt at `src/claude/spec-generator.md` contains comprehensive templates, validation checklists, and anti-pattern guidance. A skill would duplicate what the agent already enforces.

The format inconsistencies in the specs directory originate from specs not routed through spec-generator (manual creation or other bots). This is an organizational routing concern, not a spec-generator quality concern.

## Recommendation

No skill creation needed. If format consistency across all spec authors becomes a priority, consider a validation script that enforces EARS format on spec files at commit time (separate issue).
