# ADR Debate Log: ADR-034 Investigation Session QA Exemption

## Summary

- **Rounds**: 1
- **Outcome**: Consensus
- **Final Status**: proposed (ready for acceptance)

---

## Round 1 Summary

### Key Issues Addressed

1. **MADR 4.0 Compliance**: Added frontmatter, reversibility assessment, confirmation section
2. **Allowlist Security**: Removed `.agents/critique/` (loophole), added `.agents/security/` (valid investigation)
3. **Regex Fix**: Updated memory path pattern for subdirectory support
4. **Evidence Verification**: Confirmed Session 106 exists at documented path
5. **Metrics Plan**: Added measurement criteria for success tracking
6. **Ownership**: Assigned Architect agent as allowlist maintainer

### Major Changes Made

| Change | Source Agent | Rationale |
|--------|--------------|-----------|
| Add MADR 4.0 frontmatter | Architect | Format compliance |
| Remove `.agents/critique/` from allowlist | High-Level Advisor (ruling) | 5/6 agents flagged as loophole |
| Add `.agents/security/` to allowlist | Security | Valid investigation output |
| Fix memory regex `^\.serena/memories($\|/)` | Critic | Subdirectory matching |
| Add Reversibility Assessment | Architect | Required ADR section |
| Add Confirmation section | Architect | Verification criteria |
| Add Metrics Collection table | High-Level Advisor | Success measurement |
| Assign allowlist owner | High-Level Advisor | Maintenance responsibility |
| Clarify branch strategy | Analyst | Mixed-session recovery |
| Update test cases | Multiple | Reflect allowlist changes |

### Agent Positions (Final)

| Agent | Position | Notes |
|-------|----------|-------|
| Architect | Accept | All P1 issues addressed |
| Critic | Accept | P0 issues resolved (regex, critique removed) |
| Independent Thinker | Disagree-and-Commit | Notes problem severity may be overstated |
| Security | Accept | `.agents/security/` path added |
| Analyst | Accept | Session 106 verified, planning exclusion documented |
| High-Level Advisor | Accept | Metrics and owner added |

### Consensus Criteria

- 5 Accept + 1 Disagree-and-Commit = **Consensus Reached**
- No blocking concerns remain
- All P0 and P1 issues resolved

---

## Conflict Resolution Record

### Conflict 1: `.agents/critique/` in Allowlist

| Position | Agents | Outcome |
|----------|--------|---------|
| Include | 1 (original ADR) | REJECTED |
| Exclude | 5 (Architect, Critic, Independent Thinker, Analyst, High-Level Advisor) | **ACCEPTED** |

**Ruling**: EXCLUDE - Critic sessions produce plan reviews that gate implementation decisions. Including critique creates a loophole for avoiding QA on consequential artifacts.

### Conflict 2: Missing Paths in Allowlist

| Path | Decision | Rationale |
|------|----------|-----------|
| `.agents/security/` | ADD | Security assessments are investigation outputs |
| `.agents/handoffs/` | REJECT | Handoffs coordinate implementation, not investigation |
| `.agents/planning/` | REJECT | Implementation plans produce testable artifacts |

### Conflict 3: Session 106 Evidence

| Finding | Resolution |
|---------|------------|
| Analyst claimed file not found | File verified at `.agents/sessions/2025-12-30-session-106-pr-593-ci-fix.md` |
| Evidence validity | CONFIRMED - ADR evidence stands |

### Conflict 4: CI Backstop Priority

| Option | Decision |
|--------|----------|
| P1 (Independent Thinker) | REJECTED |
| P2 (Security, Current ADR) | **ACCEPTED** |

**Ruling**: Pre-commit guardrail is primary enforcement. CI backstop is defense-in-depth.

### Conflict 5: Scope Split

| Option | Decision |
|--------|----------|
| Split into ADR-034 + ADR-035 | REJECTED |
| Keep single ADR | **ACCEPTED** |

**Ruling**: Single coherent capability. Phased implementation handles complexity.

---

## Unresolved Issues

None. All blocking concerns addressed in Round 1.

---

## Next Steps

1. **Immediate**: Route to implementer for `Validate-Session.ps1` update
2. **After validator**: Update SESSION-PROTOCOL.md documentation
3. **Post-implementation**: Route to QA for validation testing
4. **Future**: Consider P2 enhancements (CI backstop, bypass logging)

---

## Files Referenced

- `.agents/architecture/ADR-034-investigation-session-qa-exemption.md` (updated)
- `.agents/sessions/2025-12-30-session-106-pr-593-ci-fix.md` (evidence verification)
- `scripts/Validate-Session.ps1` (implementation target)
- `.agents/SESSION-PROTOCOL.md` (documentation target)

---

## Debate Participants

| Agent | Role |
|-------|------|
| Architect | Structure, governance, MADR compliance |
| Critic | Gaps, risks, alignment |
| Independent Thinker | Contrarian analysis |
| Security | Threat models, guardrails |
| Analyst | Evidence verification, feasibility |
| High-Level Advisor | Priority, conflict resolution |

---

*Debate completed: 2025-12-30*
*Orchestrator: ADR Review Skill*

---

## Amendment Review (2026-07-08): Reconcile Allowlist to 8 Patterns

**PR**: #2958 (issue #2941). **Type**: documentation-accuracy amendment (no new
decision, no status transition). adr-review invoked per repo constraint "ADR
edited -> adr-review skill MUST run."

### Scope reviewed

The Amendment (2026-07-08) section plus the updated allowlist code block, the
narrowed Not Allowed table (`.agents/architecture/ADR-*` with a `REVIEW-*`
exception; `.agents/critique/` row removed), and the corrected test-case table.
Names `scripts/modules/investigation_allowlist.py` the single machine-readable
source of truth. Canonical count 5 -> 8 (three added, one redundant removed).

### Phase 1 findings (Zimmermann checklist)

- architect: amendment dated and per-pattern sourced (#831, #732); Not Allowed
  table updated in the same change so the two tables no longer contradict. PASS.
- critic: real gap, not editorial. The ADR claims a single source of truth but
  only `.github/scripts/validate_investigation_claims.py` imports the module;
  `test_investigation_eligibility.py` keeps a parallel hardcoded copy and
  `validate_session_json.py` consumes nothing. The amendment states this
  honestly rather than overclaiming. P1 (drift risk), deferred.
- independent-thinker: `^\.agents/architecture/REVIEW-` is anchored to the
  filename prefix, so ADR-* design files stay Not Allowed; scoping is tighter
  than the pre-amendment blanket entry, not looser. Removing the redundant
  `episodes/` pattern is behavior-preserving (`^\.agents/memory/` subsumes it).
- security: the allowlist only exempts documentation-class paths from a test
  gate; no auth, secret, or execution surface. Widening to review/critique
  artifacts adds no attack surface; the REVIEW-/ADR-* split keeps design
  decisions under QA. PASS.
- analyst: claims verified against the tree at branch HEAD. Module enumerates
  the 8 listed patterns; import graph matches the amendment's per-consumer
  statement; the prior revision's "all consumers import" implication was false
  and is now corrected. Evidence-backed.
- high-level-advisor: removes a live ADR-vs-code contradiction in a document
  that gates a CI check. Ship. DRY convergence is lower priority, correctly
  deferred.

### Phase 3 resolution

| Priority | Finding | Resolution |
|----------|---------|------------|
| P1 | Session-skill parallel allowlist copy can drift from the module | Deferred with tracking issue #2966 (converge + drift test) |
| P2 | `validate_session_json.py` consumes no allowlist | Documented in amendment; folded into #2966 |

No P0 issues. No Zimmermann anti-patterns triggered.

### Phase 4 vote

architect Accept, critic Accept, independent-thinker Accept, security Accept,
analyst Accept, high-level-advisor Accept. Consensus 6/6. Rounds: 1.

### Strategic review

Chesterton's Fence PASS (original purpose of the narrowed entries documented);
Path Dependence PASS (reversible by later amendment); Core vs Context N/A;
Second-System Effect PASS (reconciliation only, no feature expansion). Strategic
assessment: APPROVED.

**Verdict**: ACCEPTED. One real gap (DRY convergence) deferred to issue #2966.

*Amendment review completed: 2026-07-08*
*Orchestrator: ADR Review Skill*
