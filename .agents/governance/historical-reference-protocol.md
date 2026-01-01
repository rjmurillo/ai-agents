# Historical Reference Protocol

## Purpose

This document defines mandatory requirements for referencing historical artifacts in source control. Consistent historical references enable traceability, auditability, and future discovery of prior decisions and implementations.

---

## Mandatory Requirements

When referencing historical items checked into source control, documentation **MUST** include:

| Element | Required | Format | Example |
|---------|----------|--------|---------|
| **Date** | MUST | `YYYY-MM-DD` | `2026-01-01` |
| **Git Commit SHA** | MUST | Full or short SHA | `abc1234` or `abc1234def5678...` |
| **GitHub Issue** | MUST (if applicable) | `#NNN` with date | `#456 (2025-12-15)` |
| **GitHub PR** | SHOULD (if applicable) | `PR #NNN` | `PR #730` |

---

## Reference Formats

### Standard Historical Reference

```markdown
This pattern was established in commit `abc1234` (2026-01-01) as part of Issue #456.
```

### Reference with PR Context

```markdown
The implementation (commit `def5678`, 2025-12-15, PR #123) introduced the memory-first workflow.
```

### ADR or Architecture Decision Reference

```markdown
Per ADR-007 (commit `789abcd`, 2026-01-01, Issue #729), memory retrieval must precede reasoning.
```

### Session Log Reference

```markdown
Analysis completed in Session 121 (commit `fedcba9`, 2026-01-01, `.agents/sessions/2026-01-01-session-121.md`).
```

---

## Anti-Patterns (MUST NOT)

| Anti-Pattern | Why It Fails | Correct Alternative |
|--------------|--------------|---------------------|
| "This was done previously" | No traceability | "This was done in commit `abc123` (2025-12-01)" |
| "See ADR-007 for details" | ADR may have changed | "Per ADR-007 (commit `abc123`, 2025-12-20, Issue #729)" |
| "The original implementation..." | No discovery path | "The original implementation (commit `def456`, 2025-11-15)" |
| "As decided in the issue" | Issue number missing | "As decided in Issue #123 (2025-10-01)" |
| "Per our previous discussion" | Unverifiable | "Per discussion in PR #456 (2025-12-01)" |

---

## Scope of Application

This protocol applies to:

| Artifact Type | Location | Enforcement Level |
|---------------|----------|-------------------|
| ADR documents | `.agents/architecture/` | MUST |
| Session logs | `.agents/sessions/` | MUST |
| Serena memories | `.serena/memories/` | MUST |
| Analysis documents | `.agents/analysis/` | MUST |
| Planning documents | `.agents/planning/` | MUST |
| Retrospectives | `.agents/retrospective/` | MUST |
| Code comments | `*.ps1`, `*.md`, etc. | SHOULD |
| Commit messages | Git history | SHOULD (for related issue) |

---

## Rationale

1. **Immutability**: Git commit SHAs provide immutable artifact references
2. **Context**: Issue numbers link to discussion and decision rationale
3. **Chronology**: Dates enable understanding temporal relationships
4. **Discovery**: Future agents/developers can locate and verify claims
5. **Audit Trail**: Compliance and security reviews require traceable history

---

## Validation

### Manual Verification

When reviewing documents, check that historical references include:

- [ ] Date in `YYYY-MM-DD` format
- [ ] Git commit SHA (short or full)
- [ ] Issue number if the work originated from an issue
- [ ] PR number if referencing merged work

### Automated Validation (Future)

A validation script should detect patterns like:

```regex
# Missing commit SHA
"was done previously|original implementation|as decided" without /[a-f0-9]{7,40}/

# Missing date
/commit `[a-f0-9]+`/ without /\d{4}-\d{2}-\d{2}/

# Missing issue reference for known issue-linked work
"per ADR|per Issue" without /#\d+/
```

---

## Examples

### Session Log Entry

```markdown
| MUST | Read memory-index | [x] | memory-index (commit `178adb8`, 2026-01-01) |
```

### Memory File Reference

```markdown
## Source

- **Created**: 2026-01-01
- **Commit**: `178adb8`
- **Issue**: #730
- **Session**: 122
```

### ADR Cross-Reference

```markdown
This decision supersedes ADR-005 (commit `abc1234`, 2025-11-01, Issue #234) which used the previous approach.
```

### Retrospective Finding

```markdown
Root cause identified in Session 115 (commit `fed4321`, 2025-12-28, `.agents/sessions/2025-12-28-session-115.md`) - the validation script did not check for empty arrays.
```

---

## Related Documents

- [Naming Conventions](./naming-conventions.md) - Artifact naming patterns
- [Traceability Protocol](./traceability-protocol.md) - Specification traceability
- [SESSION-PROTOCOL.md](../SESSION-PROTOCOL.md) - Session logging requirements
- [ADR-007](../architecture/ADR-007-memory-first-architecture.md) - Memory-first architecture

---

*Version: 1.0*
*Established: 2026-01-01*
*Commit: 178adb8*
*GitHub Issue: N/A (PR #730 review feedback)*
