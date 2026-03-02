# Focus: Scope Discipline On Discovery

## Skill-Focus-001: Scope Discipline on Discovery

**Statement**: When discovery tools reveal issues outside current scope, document and defer rather than expanding scope mid-execution

**Context**: Any implementation or analysis task that uncovers additional work

**Evidence**: Found 14 violations during validation script development, explicitly deferred to maintain Phase 1 focus

**Atomicity**: 90%

**Tag**: helpful

**Impact**: 9/10

**Practice**:

1. Document discovered issue immediately
2. Create separate tracking item (issue, task, or note)
3. Add to handoff document for next session
4. Return to original scope without delay
5. Never expand scope mid-execution without explicit approval

**Pattern**:

```markdown
## Discovered Issues (Out of Scope)

| Issue | Severity | Tracking |
|-------|----------|----------|
| 14 pre-existing path violations | Medium | Issue #XX |
| Missing test coverage | Low | Backlog |

*These items deferred to maintain Phase 1 focus*
```

---