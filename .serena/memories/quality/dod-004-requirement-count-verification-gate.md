# Dod: Requirement Count Verification Gate

## Skill-DoD-004: Requirement Count Verification Gate

**Statement**: Implementation complete requires both tests passing AND requirement count verified (N implemented = N specified)

**Context**: Before marking any multi-item implementation as complete

**Evidence**: 4 of 20 items missed in personality integration without count verification gate (20% miss rate undetected until retrospective)

**Atomicity Score**: 93%

**Tag**: helpful

**Impact**: 10/10 (CRITICAL - prevents all future gap scenarios)

**Created**: 2025-12-19

**Source**: `.agents/retrospective/2025-12-19-personality-integration-gaps.md`

**Implementation**:

```markdown
## Definition of Done

### Code Complete
- [ ] All functionality implemented
- [ ] Unit tests pass
- [ ] Integration tests pass

### Requirement Verification  ← REQUIRED (NEW)
- [ ] Requirement count verified: N implemented = N specified
- [ ] Checkbox manifest 100% checked (if applicable)
- [ ] No items deferred without explicit acknowledgment
```

---