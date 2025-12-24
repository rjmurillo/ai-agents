# Security Skills Index

**Domain**: Security patterns, vulnerability prevention, and secure development
**Skills**: 10
**Updated**: 2025-12-23

## Activation Vocabulary

| Keywords | File |
|----------|------|
| multi-agent validation chain security qa devops three-phase remediation threat model | security-validation-chain |
| input validation sanitize parameterized allowlist denylist type-check injection | security-defensive-coding |
| error handling stack trace internal details generic message correlation ID | security-defensive-coding |
| logging security event audit authentication authorization access control sensitive | security-defensive-coding |
| secret detection regex pattern hardcoded AWS GitHub token API key connection string | security-secret-detection |
| infrastructure file CI CD IaC Dockerfile Kubernetes script config sensitive review | security-infrastructure-review |
| TOCTOU race condition cross-process symlink defense-in-depth re-validate action | security-toctou-defense |
| first-run gap creation exists modification conditional check bypass | security-toctou-defense |
| review triage signal quality security comment priority domain-adjusted actionable | security-review-enforcement |
| pre-commit hook bash detection ADR-005 PowerShell CWE-20 CWE-78 enforcement | security-review-enforcement |

## Coverage

| File | Skills | Focus |
|------|--------|-------|
| security-validation-chain | 001 | Multi-agent security workflow |
| security-defensive-coding | 002, 003, 004 | Input, errors, logging |
| security-secret-detection | 005 | Regex patterns for secrets |
| security-infrastructure-review | 006 | File categories for review |
| security-toctou-defense | 007, 008 | Race conditions, first-run gaps |
| security-review-enforcement | 009, 010 | Triage and pre-commit |

## Related

- Source: PRs #43, #52, #60, Session 44
- PowerShell security: `powershell-security-ai-output`
- GitHub CLI security: `github-cli-anti-patterns`
