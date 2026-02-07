# ADR-045 Debate Log: Framework Extraction via Plugin Marketplace

**Date**: 2026-02-07
**Session**: 1181
**Rounds**: 1 (initial review)
**Status**: NEEDS-REVISION

## Consolidated Verdict

**NEEDS-REVISION** (5 of 6 agents). 1 agent voted BLOCK. Direction is sound but critical gaps exist.

## Agent Verdicts

| Agent | Verdict | Confidence |
|-------|---------|------------|
| Architect | NEEDS-REVISION | High |
| Critic | NEEDS-REVISION | High (85%) |
| Independent Thinker | NEEDS-REVISION | High |
| Security | NEEDS-REVISION | High (Risk Score 7.2/10) |
| Analyst | NEEDS-REVISION | High |
| High-Level Advisor | BLOCK | High |

## P0 Issues (Must Resolve)

### P0-1: Missing ADR Template Sections (Architect)

ADR-045 lacks decision drivers, stakeholders (RACI), confirmation method, and reversibility assessment per MADR 4.0 template.

### P0-2: Timeline Conflict (Critic, Advisor)

v0.3.1 prerequisite completes Jan 2027 (12-month migration). v0.4.0 cannot start execution until then. The ADR should state this explicitly and the Gantt chart should reflect it.

### P0-3: No Validated External Demand (Independent Thinker, Advisor)

Zero evidence of external projects requesting the framework. Third-party alternatives exist (claude-flow, agents, multi-agent-shogun). This may be premature abstraction.

### P0-4: Inventory Verification Missing (Critic)

65/25/10 framework/domain/hybrid split lacks documented methodology. No grep patterns, validation script, or audit trail for classification.

### P0-5: Path Abstraction Failure Modes (Critic, Security)

Environment variables with defaults but no validation that consumer directories exist. Skills writing to consumer paths could fail silently. Security agent identified path traversal risk (CVSS 7.8): `AWESOME_AI_SESSIONS_DIR="../../.ssh"` could read SSH keys without normalization.

### P0-6: No Plugin Integrity Verification (Security)

No SHA pinning, signature verification, or cryptographic attestation for plugin distribution. Compromised plugin maintainer can inject malicious code into all consumers. CVSS 8.1 (Critical).

### P0-7: Hook Code Execution Without Sandboxing (Security)

Plugin hooks run with FULL consumer privileges (filesystem, network, secrets). Can exfiltrate credentials, modify code, execute arbitrary commands. No capability-based permission model defined. CVSS 9.1 (Critical).

### P0-8: "Zero Coupling" Claim is False (Analyst)

14 of 18 agent templates contain hard-coded `.agents/` paths (e.g., `Save to: .agents/analysis/NNN-[topic]-analysis.md`). Plan claims "zero coupling, cleanest extraction" for agents but path parameterization work is not accounted for.

### P0-9: Session Estimate 50% Underestimated (Analyst)

15-22 sessions estimated but evidence shows 30-40 minimum when accounting for: path parameterization (14 templates), PowerShell skill dependencies (40 github scripts, 13 memory files), hook conversion (12+ PowerShell hooks), namespace migration across 1700+ files.

## P1 Issues (Should Resolve)

### P1-1: Namespace Migration Verification Incomplete (Critic, Independent Thinker)

Grep sweep is insufficient for SKILL.md frontmatter (YAML), dynamic skill names (string interpolation), and external documentation references.

### P1-2: Plugin Marketplace Format Instability (Independent Thinker)

Issues #17089 and #17361 show undocumented breaking changes. ADR should include stability monitoring plan and rollback strategy.

### P1-3: Two-Repo Maintenance Cost Underestimated (Independent Thinker)

ADR lists "two repos" as negative consequence but does not quantify: 2x CI/CD, 2x dependency management, cross-repo coordination for breaking changes.

### P1-4: Prerequisite Completion Criteria Missing (Critic)

v0.3.0 and v0.3.1 are prerequisites but no acceptance criteria defined for "complete."

### P1-5: Capacity Conflict (Advisor)

Single maintainer with 3 concurrent milestones (v0.3.0, v0.3.1, v0.4.0). Planning v0.4.0 before v0.3.0 ships risks stalling all three.

### P1-6: Reversibility and Vendor Lock-in (Architect)

No exit strategy documented. Claude Code plugin marketplace is the sole distribution point. Need rollback plan (git submodules, npm).

### P1-7: No Secret Masking in Plugin Hooks (Security)

Hooks execute with access to consumer environment variables and can log or transmit secrets without detection. No secret masking, audit logging, or sensitive data filtering specified. CVSS 6.8.

### P1-8: CI Workflow Templates Without SHA Pinning (Security)

Templates distributed with mutable version tags (@v4). Violates existing PROJECT-CONSTRAINTS.md security requirement. CVSS 7.4.

### P1-9: No Rollback Mechanism for Plugin Updates (Security)

No documented recovery path if a plugin update introduces security vulnerability or breaking change.

### P1-10: 4-Plugin vs 2-Plugin Model (Analyst)

4 plugins may be over-engineering. Consider consolidating to core (agents + templates) and extensions (skills + protocol + gates) to reduce 4x maintenance overhead.

## P2 Issues (Consider)

### P2-1: 4-Plugin Granularity Lacks Usage Analysis (Critic)

No evidence of which plugin combinations consumers would use. If 90%+ install all 4, consolidate to fewer.

### P2-2: Namespace "awesome-ai" Concerns (Advisor)

Name communicates nothing about multi-agent frameworks. Consider `multi-agent-framework` or `claude-agent-system`.

### P2-3: Memory Router Extraction Complexity (Critic)

Memory skills reference consumer paths (`.serena/memories/`) and external MCP endpoints. May need special handling.

## Strengths Acknowledged

All agents agreed on these positives:

- Strong research foundation (session 1180 plugin marketplace analysis)
- Correct prerequisite sequencing (Python migration before extraction)
- Plugin marketplace is the right distribution mechanism
- 4-plugin granularity is reasonable (though needs validation)
- Plan is detailed and well-structured

## Dissent Record

**High-Level Advisor (BLOCK)**: Argued that v0.4.0 planning should be deferred entirely until v0.3.1 reaches 50% completion. Recommends closing epic #1072 and refocusing on v0.3.0/v0.3.1 execution. Considers this "architecture astronautics" without proven demand.

**Counterpoint**: The plan explicitly documents v0.3.0 and v0.3.1 as hard prerequisites. Planning documentation does not block execution of other milestones. The ADR status is "Proposed" (not "Accepted"), which is appropriate for forward-looking architecture work.

## Resolution Path

1. Address P0 issues (9 total) in ADR-045 revision
2. Add Security Model section to ADR (supply chain, hook permissions, path security)
3. Revise session estimate to 30-40 and add explicit timeline (start: Q1 2027)
4. Create rigorous file-by-file inventory with classification criteria
5. Resubmit for Round 2 review
6. If all agents reach ACCEPT or D&C, change ADR status to Accepted

## Next Steps

- ADR-045 remains in "Proposed" status
- Critique saved to `.agents/critique/ADR-045-critique.md` (by critic agent)
- Security review saved to `.agents/security/ADR-045-framework-extraction-security-review.md`
- Feasibility analysis saved to `.agents/analysis/adr-045-feasibility-analysis.md`
- v0.4.0 execution is blocked until v0.3.0 and v0.3.1 prerequisites met
- Planning artifacts (PLAN.md, issues, milestone) are valid forward-looking work
