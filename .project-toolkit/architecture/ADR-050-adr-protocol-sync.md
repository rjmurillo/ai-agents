---
id: ADR-050
status: deprecated
date: 2026-10-13
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
---

# ADR-050: ADR-to-Protocol Sync Process

## Status

Deprecated (2026-10-13). The frontmatter `date` is the deprecation date; the
`## Date` section below stays the original decision date.

PR #5179 removed the session protocol on 2026-08-20, in commit
`ba541c21`. That change deleted both halves of this decision: the audit script
`scripts/sync_adr_protocol.py` and the document it synced against,
`.agents/SESSION-PROTOCOL.md`. The requirement to propagate ADR requirements
into the protocol no longer holds, because the target document is gone. The
Decision and Implementation Notes below are kept as written, as the record of
what was decided.

Rebuilding the script was rejected. It needs the protocol document back first,
and PR #5179 retired that document on purpose. Retargeting the process at a
surviving document, such as `AGENTS.md` or `.claude/rules/`, is a new decision.
It belongs in a new ADR that supersedes this one, not in an edit to this record.
This record is `deprecated`, not `superseded`: it shipped, it was abandoned,
and no successor decision names it.

Issue #5194 found the stale `accepted` status. The `cited-paths-exist` check in
`scripts/validation/check_adr_lifecycle.py` now flags this drift in any accepted
record.

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
