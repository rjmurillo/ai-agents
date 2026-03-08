---
description: Run security assessment on implementation results. Mandatory for security-tagged issues. Covers OWASP, secrets, and dependencies.
argument-hint: <review scope>
model: sonnet
---

# /4-security — Security Review

Run security assessment on implementation results.

## Purpose

Identify vulnerabilities, verify security best practices, and ensure compliance with security standards. **Mandatory** for issues tagged with security labels.

## Actions

1. **OWASP Top 10 check** — Scan for common web application vulnerabilities
2. **Secret detection** — Verify no credentials, API keys, or tokens in code
3. **Dependency audit** — Check for known vulnerabilities in dependencies
4. **Input validation review** — Verify all user inputs are sanitized
5. **Generate security report** — Structured findings with severity ratings

## Agent Routing

Routes to the **security** agent (Tier 3: Builder).

```text
security agent
├── OWASP Top 10 assessment
├── Secret/credential scanning
├── Dependency vulnerability audit
├── Input validation review
└── Security report generation
```

For critical findings, the security agent escalates to the **architect** (Tier 1: Expert) for design-level security decisions.

## MCP Integration

Maps to Agent Orchestration MCP (ADR-013):

- `invoke_agent("security", prompt)` — dispatch security review
- `track_handoff(from="qa", to="security", context)` — preserve QA context

**Mandatory invocation**: When an issue has a `security` label, the Agent Orchestration MCP enforces that `/4-security` cannot be skipped.

**Fallback**: Direct `Task(subagent_type="security", prompt=...)` invocation.

## Security Checklist

| Check | Severity | Description |
|-------|----------|-------------|
| No hardcoded secrets | CRITICAL | No API keys, passwords, tokens in source |
| Input validation | HIGH | All user inputs sanitized and validated |
| Authentication checks | HIGH | Protected endpoints require auth |
| Authorization checks | HIGH | Role-based access enforced |
| Dependency vulnerabilities | MEDIUM | No known CVEs in dependencies |
| OWASP Top 10 | MEDIUM | No common vulnerability patterns |
| Logging sensitive data | MEDIUM | No PII or secrets in logs |
| Error handling | LOW | No stack traces or internal details exposed |

## Output

- **Security Report** — Findings with severity (CRITICAL / HIGH / MEDIUM / LOW)
- **Vulnerability List** — Specific issues with file locations and line numbers
- **Dependency Audit** — CVE report for third-party packages
- **Recommendation** — Proceed to `/9-sync` or return to `/2-impl` for remediation

## Sequence Position

```text
/0-init → /1-plan → /2-impl → /3-qa → ▶ /4-security → /9-sync
```

## Dependencies

- Agent Orchestration MCP Phase 1 (ADR-013) — mandatory invocation enforcement
- Requires implementation from `/2-impl` (may also use QA results from `/3-qa`)

## Examples

```text
/4-security Review the OAuth2 implementation for vulnerabilities
/4-security Run full security audit on the new API endpoints
```
