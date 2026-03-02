# Documentation: Templatefirst Documentation Workflow

## Skill-Documentation-001: Template-First Documentation Workflow

**Statement**: Agent document changes must go through templates then Generate-Agents.ps1 to maintain consistency

**Context**: When updating agent guidelines, protocols, or documentation that affects multiple agent variants

**Evidence**: AGENTS.md naming conventions section added via templates/agents/orchestrator.shared.md then Generate-Agents.ps1

**Atomicity**: 94%

**Tags**: documentation, workflow, templates, agents

**Rationale**: Maintains consistency across Claude Code, Copilot CLI, and VS Code agent variants

**Workflow**:

1. Edit `templates/agents/[agent].shared.md`
2. Run `pwsh scripts/Generate-Agents.ps1`
3. Verify changes in all agent variants:
   - `src/claude/*.md`
   - `src/copilot-cli/*.agent.md`
   - `src/vs-code-agents/*.agent.md`
4. Commit all updated files together

---

## Success Patterns Validated

### Test-Driven Development for Validation Scripts

- **Evidence**: Both bugs (case-sensitivity, hashtable syntax) caught by tests before integration
- **Impact**: High - prevented production issues
- **Validation Count**: 1

### Atomic Commits with Conventional Format

- **Evidence**: 3 commits, all atomic and well-formatted
- **Impact**: High - enables easy review and rollback
- **Validation Count**: 3

### Non-Blocking Pre-Commit Warnings

- **Evidence**: No workflow disruption reported, users receive feedback
- **Impact**: Medium - raises awareness without blocking
- **Validation Count**: 2 (this validation + previous planning validation)

---

## Related

- [documentation-001-systematic-migration-search](documentation-001-systematic-migration-search.md)
- [documentation-002-reference-type-taxonomy](documentation-002-reference-type-taxonomy.md)
- [documentation-003-fallback-preservation](documentation-003-fallback-preservation.md)
- [documentation-004-pattern-consistency](documentation-004-pattern-consistency.md)
- [documentation-006-self-contained-operational-prompts](documentation-006-self-contained-operational-prompts.md)
