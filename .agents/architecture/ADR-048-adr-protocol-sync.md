# ADR-048: ADR-to-Protocol Sync Process

## Status

Accepted

## Date

2026-02-21

## Context

ADRs define governance decisions with MUST/SHOULD/MAY requirements per RFC 2119. SESSION-PROTOCOL.md is the canonical enforcement document that agents follow during sessions. These two systems operate independently, creating a gap: ADRs can introduce MUST requirements that never appear in SESSION-PROTOCOL.md.

Example: ADR-042 mandates Python for new scripts. ADR-035 requires exit code documentation in script headers. Neither requirement appears in SESSION-PROTOCOL.md. Agents follow SESSION-PROTOCOL.md, not individual ADRs, so these requirements go unenforced.

The root cause is the absence of a defined process to propagate ADR requirements into SESSION-PROTOCOL.md.

## Decision

**Establish a two-tier ADR-to-Protocol sync process: an automated audit script and a manual integration checklist.**

### Automated Audit Script

A Python script (`scripts/sync_adr_protocol.py`) parses all ADR files, extracts RFC 2119 requirements (MUST, MUST NOT, SHOULD, SHOULD NOT, MAY), and checks whether SESSION-PROTOCOL.md references each ADR. The script reports:

- ADRs with MUST requirements not referenced in SESSION-PROTOCOL.md
- Total requirement counts per ADR
- A summary of sync coverage

### Manual Integration Checklist

When creating or updating an ADR with MUST requirements:

1. Author identifies MUST requirements in the Decision section
2. Author adds a "Protocol Integration" section to the ADR listing which SESSION-PROTOCOL.md sections need updates
3. Author updates SESSION-PROTOCOL.md with the new requirements
4. The sync script runs in CI to catch missed integrations

### ADR Template Update

The ADR template gains an optional "Protocol Integration" section for ADRs that introduce enforceable requirements.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| No sync (status quo) | Zero effort | Requirements go unenforced, governance gap grows | Demonstrated failure with ADR-042 and ADR-035 |
| Fully automated sync | No manual steps | Requires NLP to map requirements to protocol sections, brittle | Over-engineering for 47 ADRs |
| ADR-embedded enforcement | Self-contained | Fragments protocol across 47+ files, harder for agents to follow | Single source of truth principle violated |

### Trade-offs

**Manual integration vs full automation:** The manual step requires ADR authors to update SESSION-PROTOCOL.md. The automated script catches omissions. This balances effort with reliability.

**Audit granularity:** The script checks ADR-level references in SESSION-PROTOCOL.md, not individual requirement-level mapping. Requirement-level mapping would require semantic understanding of protocol sections. ADR-level reference checking is sufficient to flag gaps.

## Consequences

### Positive

- Closes the governance-to-enforcement gap for new ADRs
- Existing gaps become visible through audit output
- CI enforcement prevents future drift

### Negative

- Manual integration step adds work to ADR creation
- Script produces false positives for ADRs without enforceable requirements (informational ADRs)

### Neutral

- Existing ADRs need one-time audit (backlog, not blocking)

## Implementation Notes

### Script Location

`scripts/sync_adr_protocol.py` following ADR-042 (Python for new scripts).

### CI Integration

Run the sync script in CI as a non-blocking check initially. Promote to blocking after backlog of existing gaps is resolved.

### Exit Codes

Per ADR-035:

- 0: All ADRs with MUST requirements are referenced in SESSION-PROTOCOL.md
- 1: Gaps detected (ADRs with MUST requirements not referenced)
- 2: Configuration or file access error

## Related Decisions

- ADR-035: Exit Code Standardization (exit code contract)
- ADR-042: Python Migration Strategy (script language choice)
- ADR-043: Scoped Tool Execution (example of ADR successfully synced to protocol)

## References

- Issue #941: Create ADR-to-Protocol sync process
- RFC 2119: Key words for use in RFCs to indicate requirement levels
- `.agents/SESSION-PROTOCOL.md`: Canonical session protocol

---

*Created: 2026-02-21*
*GitHub Issue: #941*
