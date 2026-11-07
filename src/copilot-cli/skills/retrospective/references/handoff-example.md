# Example Handoff Output

Filled example of the structured handoff block the `retrospective` agent ends with (Claude Code
only). Read it when you write the block and want a reference for the table shapes. The block
contract and output rules stay in the agent body.

````markdown
## Retrospective Handoff

### Skill Candidates

| Skill ID | Statement | Atomicity | Operation | Target |
|----------|-----------|-----------|-----------|--------|
| validation-yaml-syntax | Validate workflow YAML syntax before committing | 92% | ADD | - |
| ci-matrix-parallel | Use matrix strategy for parallel agent execution | 88% | UPDATE | skills-ci-infrastructure.md |

### Memory Updates

| Entity | Type | Content | File |
|--------|------|---------|------|
| AI-Workflow-Patterns | Pattern | Parallel matrix reduces execution time by 50% | `.serena/memories/skills-ci-infrastructure.md` |
| Session-17-Learnings | Learning | Structured handoff format enables automation | `.serena/memories/learnings-2025-12.md` |

### Git Operations

| Operation | Path | Reason |
|-----------|------|--------|
| git add | `.serena/memories/skills-ci-infrastructure.md` | Updated with 2 skills |
| git add | `.serena/memories/learnings-2025-12.md` | New monthly learnings |
| git add | `.project-toolkit/retrospective/2025-12-18-workflow-retro.md` | Retrospective artifact |

### Findings for the owner

| Item | Evidence (path:line) | Proposed action | Class |
|------|----------------------|-----------------|-------|

### Handoff Summary

- **Skills to persist**: 2 candidates (atomicity >= 70%)
- **Memory files touched**: skills-ci-infrastructure.md, learnings-2025-12.md
- **Blockers for the owner**: 0
- **Recommended next**: skillbook -> memory -> git add
````
