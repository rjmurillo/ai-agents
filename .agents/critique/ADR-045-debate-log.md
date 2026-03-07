# ADR-045 Debate Log: Framework Extraction via Plugin Marketplace

**Date**: 2026-02-07
**Session**: 1181
**Rounds**: 2
**Status**: ACCEPTED

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

---

## Round 2

### Consolidated Verdict

**ACCEPTED** (3 Accept + 3 Disagree-and-Commit). No BLOCKs. Consensus threshold met.

All 9 P0 issues from Round 1 confirmed resolved. Security risk score improved from 7.2/10 to 3.8/10.

### Agent Verdicts (Round 2)

| Agent | Verdict | Confidence | Key Finding |
|-------|---------|------------|-------------|
| Architect | ACCEPT | High | All P0 resolved. 4 P2 formatting items (MADR YAML frontmatter, confirmation ownership, hook permission wording, alternatives table format). |
| Critic | ACCEPT | 85% | All P0 resolved. 3 minor implementation-detail gaps (CI script location, namespace match count, traversal test patterns). |
| Independent Thinker | DISAGREE-AND-COMMIT | High | Missing "in-repo directory reorganization" alternative. Plugin format instability (issues #17089, #17361 verified as open). |
| Security | ACCEPT | High (3.8/10 risk) | All P0/P1 security issues resolved. Hook sandboxing downgraded to P2 accepted risk. STRIDE analysis updated. safe_resolve() validated. |
| Analyst | DISAGREE-AND-COMMIT | 90% | P1-10 (2-plugin model) partially addressed. Recommends Phase 0 checkpoint for plugin consolidation evaluation. Hybrid percentage justification qualitative not quantitative. |
| High-Level Advisor | DISAGREE-AND-COMMIT | High | Dissents on cost-benefit grounds. 30-39 sessions for single-consumer framework is poor ROI. Condition: Add "in-repo directory reorganization" as evaluated alternative. |

### P0 Resolution Verification

All 9 P0 issues from Round 1 confirmed resolved by all 6 agents:

| P0 Issue | Resolution | Verified By |
|----------|-----------|-------------|
| P0-1: Missing ADR sections | Added Decision Drivers, Stakeholders, Confirmation, Reversibility | Architect |
| P0-2: Timeline conflict | Explicit Q1 2027 start, v0.3.1 prerequisite with Jan 2027 completion | Critic, Advisor |
| P0-3: No external demand | Honest acknowledgment in Context section, "What this is NOT" paragraph | Independent Thinker |
| P0-4: Inventory verification | 168-file audit with methodology, verification script requirement | Critic |
| P0-5: Path abstraction failures | safe_resolve() with containment check, descriptive exceptions, validation requirements | Critic, Security |
| P0-6: No plugin integrity | SHA/tag pinning mandate, explicit consumer action for updates, SHA-pinned Actions | Security |
| P0-7: Hook sandboxing | Documented as Claude Code platform characteristic, review recommendation, future adoption commitment | Security |
| P0-8: False "zero coupling" | Corrected to "Low coupling" with 14/18 template parameterization quantified | Analyst |
| P0-9: Session underestimate | Revised to 30-39 sessions with formal inventory backing | Analyst |

### Remaining Issues (Non-Blocking)

#### New P1 from Round 2

**P1-NEW-1: Missing "in-repo directory reorganization" alternative** (Independent Thinker, High-Level Advisor)

The alternatives table did not evaluate the simpler option of reorganizing directories within the existing repo (e.g., `framework/` + `project/` with clear module boundaries) without extracting to a separate repository. This achieves separation of concerns without two-repo overhead but does not dog-food the plugin format.

**Resolution**: Added to Alternatives Considered table in ADR-045 with explicit evaluation of why it was not chosen.

#### P2 Items (Non-Blocking)

- Architect: MADR YAML frontmatter, confirmation ownership, hook permission wording, alternatives table format
- Critic: CI script exact location, namespace migration match count, traversal test edge cases
- Analyst: Phase 0 checkpoint for 2-plugin vs 4-plugin re-evaluation

### Dissent Record (Round 2)

**Independent Thinker (D&C)**: Accepts the direction but maintains that plugin format instability (issues #17089 and #17361) represents real risk. The in-repo directory reorganization alternative should have been evaluated from the start. Commits because the ADR honestly acknowledges no external demand and the prerequisite sequencing is correct.

**Analyst (D&C)**: All claims now evidence-backed. The 37% hybrid percentage justification could be more quantitative, but the re-evaluation decision (proceed because path parameterization is one-time cost) is reasonable. Recommends Phase 0 include explicit plugin count re-evaluation checkpoint.

**High-Level Advisor (D&C, Round 2)**: Maintained this was over-investment for a single-consumer project. Committed because Q1 2027 timeline means no capacity consumed until v0.3.1 completes.

**High-Level Advisor (ACCEPT, Round 2.5)**: Vote upgraded from D&C to ACCEPT after context correction. The ADR originally stated "no validated external demand" and "single-maintainer project," which were factually wrong. Corrected context: ~400 target users in organizational rollout within 30 days of extraction. This transforms the cost-benefit from 30 sessions / 1 consumer to 30 sessions / 400 consumers. Plugin marketplace is justified as distribution infrastructure, not a validation exercise. All three D&C pillars invalidated or weakened: (1) ROI justified by 400 consumers, (2) distribution replaces dog-fooding, (3) 453 commits in 2 months demonstrates execution velocity despite 11-month prerequisite. Recommends Phase 0 gate to confirm organizational rollout is still on track.

### Round 2 Conclusion (Updated)

Final tally: **4 ACCEPT** (Architect, Critic, Security, High-Level Advisor) + **2 D&C** (Independent Thinker, Analyst). No BLOCKs.

High-Level Advisor upgraded from D&C to ACCEPT in Round 2.5 after ADR corrected to reflect organizational scaling context (~400 users, distribution mechanism, project velocity).

**ADR-045 status: Accepted.**

D&C conditions addressed:
1. "In-repo directory reorganization" added to Alternatives Considered table
2. Phase 0 checkpoint for plugin consolidation documented in PLAN.md scope
3. Organizational context corrected (400 users, distribution mechanism)
4. All dissent formally recorded in this log
