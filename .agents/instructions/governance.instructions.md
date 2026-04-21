---
applyTo: ".agents/governance/**"
priority: high
---

# Governance File Rules

Files under `.agents/governance/` define the rules that bind every other agent role. Changes here have system-wide reach.

## MUST

1. **Human approval** — Changes MUST be reviewed and approved by a human maintainer. Auto-merge is prohibited for governance files.
2. **ADR required** — Significant governance changes (new rules, policy reversals, removed constraints) MUST be accompanied by an Architecture Decision Record in `.agents/architecture/`.
3. **Consensus for cross-role rules** — Changes that affect multiple agent roles MUST follow the consensus protocol in `CONSENSUS.md` (domain-weighted voting; security gets 2.0x on security decisions).
4. **Evidence required** — Every rule change MUST cite the failure mode, retrospective, or incident that motivated it. Add a `Why:` section if rationale is not obvious.
5. **No unilateral changes** — A single specialist agent MUST NOT alter rules that govern other agents without consensus.

## SHOULD

1. **Update canonical sources first** — `PROJECT-CONSTRAINTS.md` is the index of record. New constraints SHOULD land there, with details in a dedicated governance file.
2. **Cross-link** — SHOULD link new governance content from `AGENTS.md` and `CLAUDE.md` when it affects agent defaults.
3. **RFC 2119** — Rules SHOULD use MUST / SHOULD / MAY to state requirement strength explicitly.

## MUST NOT

1. MUST NOT reduce security or review requirements without a unanimous-consensus ADR.
2. MUST NOT remove the evidence link for an existing rule. Supersession requires a new ADR, not silent deletion.

## References

- `.agents/governance/PROJECT-CONSTRAINTS.md` — canonical constraints index
- `.agents/governance/CONSENSUS.md` — consensus algorithms and weights
- `.agents/governance/FAILURE-MODES.md` — historical motivations
- `.agents/architecture/ADR-*.md` — decision records
