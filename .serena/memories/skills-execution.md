# Execution & Focus Skills

**Extracted**: 2025-12-16
**Source**: `.agents/retrospective/phase1-remediation-pr43.md`

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

## Skill-Execution-001: Ship MVP Over Perfect

**Statement**: Choose "working and shippable" over "perfect" when time-constrained, documenting enhancements as technical debt

**Context**: Implementation decisions under time pressure

**Evidence**: Simple validation script shipped vs. sophisticated parser with code fence detection (deferred to Phase 3)

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 8/10

**Decision Framework**:

1. Does it solve the immediate problem? → Yes = ship
2. Are known limitations documented? → Must be yes
3. Is there a path to enhancement? → Document in backlog
4. Does shipping create tech debt? → Acceptable if tracked

**Anti-Pattern**:

- Gold-plating features that aren't required
- Delaying ship for edge cases
- Perfect being enemy of good
- Undocumented shortcuts

---

## Related Documents

- Source: `.agents/retrospective/phase1-remediation-pr43.md`
- Related: skills-workflow (Skill-Workflow-004 atomic commits)
