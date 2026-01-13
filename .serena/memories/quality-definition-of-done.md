# Definition of Done Skills

**Statement**: Definition of Done must include documentation, handoffs, and blocker identification

**Context**: Planning artifacts, DoD checklists

**Evidence**: CVA plan included documentation but it was dropped because DoD was code-focused

**Atomicity**: 92%

**Impact**: 9/10

## Standard DoD Template

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

### Requirement Verification ← REQUIRED
- [ ] Requirement count verified: N implemented = N specified
- [ ] Checkbox manifest 100% checked (if applicable)
```

## Explicit Agent Handoffs

When a plan identifies multiple agent types, create explicit handoff checkpoints:

```markdown
## Execution Handoffs

1. implementer → code complete
   - [ ] Handoff to: **qa** for verification

2. qa → tests pass
   - [ ] Handoff to: **explainer** for documentation

3. explainer → docs complete
   - [ ] Handoff to: **retrospective** for learning
```

## Action Item Blocking

- User-facing gaps (docs, UX) = **BLOCKER** status
- Internal cleanup = can be deferred
- Session cannot close with BLOCKER items incomplete

## Related

- [quality-agent-remediation](quality-agent-remediation.md)
- [quality-basic-testing](quality-basic-testing.md)
- [quality-critique-escalation](quality-critique-escalation.md)
- [quality-prompt-engineering-gates](quality-prompt-engineering-gates.md)
- [quality-qa-routing](quality-qa-routing.md)
