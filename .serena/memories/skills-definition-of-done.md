# Definition of Done Skills

**Extracted**: 2025-12-16
**Source**: `.agents/retrospective/2025-12-15-documentation-gap.md`

## Skill-DoD-001: Documentation in Definition of Done

**Statement**: Include documentation deliverables in the Definition of Done for any user-facing feature

**Context**: Planning artifacts, DoD checklists

**Evidence**: CVA plan included documentation but it was dropped because DoD was code-focused

**Atomicity**: 92%

**Tag**: helpful

**Impact**: 9/10

**Pattern**:

```markdown
## Definition of Done

### Code Complete
- [ ] All functionality implemented
- [ ] Unit tests pass
- [ ] Integration tests pass

### Documentation Complete  ← REQUIRED
- [ ] README updated
- [ ] API docs generated
- [ ] Usage examples provided
- [ ] Changelog entry added
```

---

## Skill-DoD-002: Explicit Agent Handoffs

**Statement**: When a plan identifies multiple agent types, create explicit handoff checkpoints to ensure all agents are invoked

**Context**: Multi-agent execution plans

**Evidence**: Plan said "(explainer)" for documentation but no handoff occurred during execution

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 8/10

**Pattern**:

```markdown
## Execution Handoffs

1. implementer → code complete
   - [ ] Handoff to: **qa** for verification
   
2. qa → tests pass
   - [ ] Handoff to: **explainer** for documentation
   
3. explainer → docs complete
   - [ ] Handoff to: **retrospective** for learning extraction
```

---

## Skill-DoD-003: Action Item Blocking

**Statement**: Mark incomplete action items as blockers if they represent user-facing gaps

**Context**: Session completion and handoff

**Evidence**: Documentation marked incomplete but session ended anyway

**Atomicity**: 85%

**Tag**: helpful

**Impact**: 7/10

**Implementation**:

- User-facing gaps (docs, UX) = **BLOCKER** status
- Internal cleanup = can be deferred
- Technical debt = document and schedule
- Session cannot close with BLOCKER items incomplete

---

## Related Documents

- Source: `.agents/retrospective/2025-12-15-documentation-gap.md`
- Related: skills-workflow (Skill-Workflow-003 pre-implementation validation)
