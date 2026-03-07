# Skill-Memory-001: User Feedback Retrieval

## Statement

Before executing scripts or making similar changes, search Serena memory for previous user feedback on that topic

## Context

- **When to apply**: Before script execution, file generation, or similar repeated actions
- **Trigger**: About to perform action that may have been done before or that user has preferences about
- **Priority**: P1 - BLOCKING similar actions

## Evidence

**Session 2025-12-17**: User previously instructed NOT to include auto-generated headers, feedback not retrieved before executing generation script

### What happened

- User had previously provided explicit feedback: "NOT to include auto-generated headers in files"
- This feedback was NOT retrieved before executing generation script
- Script generated files with auto-generated headers
- Violated explicit user requirement
- User had to remind: "The user had previously told me NOT to include auto-generated headers"

### Impact

- Repeated mistake that user had already corrected
- User frustration (explicit mention of "repeat mistakes")
- Eroded trust
- Created reactive work instead of proactive prevention

## Atomicity Score

93%

## Category

Memory Retrieval

## Implementation Checklist

Before script execution or similar actions:

1. [ ] Identify the type of action (e.g., "file generation", "code formatting", "header insertion")
2. [ ] Search Serena memory for keywords related to that action
3. [ ] Look for previous user feedback, preferences, or instructions
4. [ ] If feedback found: verify current action aligns with it
5. [ ] If feedback conflicts: ask user for clarification before proceeding
6. [ ] Only after verification: proceed with action

## Search Query Examples

- Before generating files: Search for "generate", "headers", "file creation"
- Before formatting code: Search for "format", "style", "indentation"
- Before committing: Search for "commit", "message format", "git"

## Related Skills

- DEPENDS ON: Skill-Init-001 (Serena must be initialized for memory access)
- SUPPORTS: Skill-Verify-001 (provides requirements for audit)
- PREVENTS: Repeat mistakes based on previous feedback

## Tags

- #memory
- #user-feedback
- #requirements
- #prevention
- #serena-memory
- #context-retrieval

## Related

- [memory-architecture-serena-primary](memory-architecture-serena-primary.md)
- [memory-index](memory-index.md)
- [memory-size-001-decomposition-thresholds](memory-size-001-decomposition-thresholds.md)
- [memory-system-fragmentation-tech-debt](memory-system-fragmentation-tech-debt.md)
- [memory-token-efficiency](memory-token-efficiency.md)
