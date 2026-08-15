# ADR Debate Log: Govern Copilot CLI Compatibility Through Executable Surfaces

## Summary

- **Rounds**: 2
- **Outcome**: Consensus
- **Final Status**: accepted
- **ADR**: `.agents/architecture/ADR-094-govern-copilot-cli-compatibility.md`

## Round 1 Summary

### Key Issues Addressed

- The first draft rewrote an implemented ADR in place.
- The validator was described as an allowlist and version authority, but it is a one-target known-bad guard.
- Runtime version mismatch was described as blocking, but the installer reports a warning.
- `CONTRIBUTING.md` and the Serena runbook still recommended blocked version `0.0.397`.
- ADR-044 carried stale model identifiers, agent counts, and frontmatter claims.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Block |
| critic | Block |
| independent-thinker | Block |
| security | Disagree-and-Commit |
| analyst | Block |
| high-level-advisor | Block |

### Resolution

The in-place rewrite was discarded. A new ADR was created to supersede ADR-044. ADR-044's original decision text was restored. The new ADR assigns version ownership to executable surfaces, narrows the validator contract, records warn-only runtime drift, defers model policy to ADR-080, and retires `0.0.397`. Contributor guidance and the regression runbook were corrected in the same change.

## Round 2 Summary

### Key Issues Addressed

- ADR-044 and ADR-094 now form a bidirectional supersession pair.
- The required review and nightly smoke versions have separate, explicit owners.
- Validator scope and limitations match the current Python implementation.
- Current 1.0.63 compatibility evidence cites session 2586.
- Historical model and agent-count claims remain only in the superseded record.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept |
| critic | Accept |
| independent-thinker | Accept |
| security | Accept |
| analyst | Accept |
| high-level-advisor | Accept |

### Dissent Record

None. All Round 1 blocking findings were resolved.

## Final Decision

ADR-094 is accepted. ADR-044 is superseded and retained as historical evidence.

## Post-Review Correction: Cross-Reference Update

### Change

Update ADR-064 references from superseded ADR-044 to current ADR-094.

### Rationale

ADR-064 lines 162 and 274 referenced ADR-044 for Copilot CLI frontmatter constraints.
Since ADR-094 supersedes ADR-044, readers following these references would land on
retired guidance. Correcting the pointers is a mechanical cross-reference fix.

### Agent Positions

| Agent | Position |
|-------|----------|
| implementer | Accept (reference-only change) |

### Outcome

Accepted. No decision change in ADR-064; only link targets updated.

