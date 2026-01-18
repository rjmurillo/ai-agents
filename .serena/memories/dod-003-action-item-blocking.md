# Dod: Action Item Blocking

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