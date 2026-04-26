---
applyTo: ".agents/security/**,**/Auth/**,*.env*,**/*.secrets.*,.github/workflows/**,.githooks/**"
priority: critical
---

# Security File Rules

These paths hold threat models, benchmarks, workflows, and hooks that protect the supply chain. Changes need evidence, not opinion.

## MUST

1. **Security agent review** — Changes MUST be reviewed by the `security` agent (or a human with equivalent authority) before merge. Security review is always-on and cannot be skipped.
2. **Evidence-based** — Every change MUST cite a CVE, CWE, OWASP reference, ADR, or documented threat. No speculative hardening.
3. **No secrets** — MUST NOT commit credentials, tokens, signing keys, or API keys. Use the configured secrets manager.
4. **Pin Actions to SHA** — Workflow changes MUST pin every third-party Action to a commit SHA. Floating tags (`@v4`, `@main`) are prohibited.
5. **Threat model updates** — Changes that introduce new attack surface MUST update the relevant benchmark under `.agents/security/benchmarks/` or cite why no update is required.
6. **Test coverage** — Security-critical code MUST have 100% coverage per `AGENTS.md` standards.

## SHOULD

1. **Run security scan locally** — SHOULD run `scripts/validation/security_scan.py` or the `security-scan` skill before pushing.
2. **Use the `security-detection` skill** — SHOULD detect security-relevant file changes via the skill and route to the security agent.
3. **Threat modeling** — SHOULD use the `threat-modeling` skill (OWASP STRIDE) for non-trivial changes.

## MUST NOT

1. MUST NOT lower severity thresholds in `SECURITY-SEVERITY-CRITERIA.md` without governance ADR.
2. MUST NOT skip security checks in CI.
3. MUST NOT merge security-sensitive changes without explicit approval, even when auto-merge labels are applied.

## References

- `.agents/governance/SECURITY-REVIEW-PROTOCOL.md` — review gates
- `.agents/governance/SECURITY-SEVERITY-CRITERIA.md` — severity thresholds
- `.agents/steering/security-practices.md` — OWASP patterns
- `.claude/skills/security-scan/` — scanner skill
- `.claude/skills/threat-modeling/` — STRIDE workflow
