# Security Severity Criteria

> **Purpose**: Standardized CVSS-based severity classification for security agent findings.
> **Source**: Issue #756 (Security Agent Detection Gaps Remediation)

## CVSS v3.1 Base Score Thresholds

| Severity | CVSS Range | Description | Response Time |
|----------|------------|-------------|---------------|
| CRITICAL | 9.0-10.0 | Immediate exploitation likely, severe impact | Block merge, fix within 24 hours |
| HIGH | 7.0-8.9 | Exploitation feasible, significant impact | Block merge, fix within 7 days |
| MEDIUM | 4.0-6.9 | Exploitation requires conditions, moderate impact | Track in issue, fix within 30 days |
| LOW | 0.1-3.9 | Limited impact, exploitation difficult | Document, fix opportunistically |

## Threat Actor Context Matrix

Severity adjustments based on deployment context and threat actor capabilities.

| Base Severity | Local CLI Tool | Remote Service |
|---------------|----------------|----------------|
| CRITICAL (9.0+) | CRITICAL (no change) | CRITICAL (+0.5 max 10.0) |
| HIGH (7.0-8.9) | HIGH (no change) | CRITICAL (+1.0 to +2.0) |
| MEDIUM (4.0-6.9) | MEDIUM (no change) | HIGH (+1.0 to +2.0) |
| LOW (0.1-3.9) | LOW (no change) | MEDIUM (+1.0) |

### Context Definitions

**Local CLI Tool**: Scripts executed by authenticated users on their own machines. Attacker must have prior local access or social engineer the user.

**Remote Service**: Network-accessible services (APIs, webhooks, web applications). Attacker can interact remotely without authentication.

## Severity Elevation Rules

Apply these modifiers after calculating CVSS base score:

| Condition | Modifier | Rationale |
|-----------|----------|-----------|
| Local exploit + privileged execution | +2.0 | Root/admin escalation increases blast radius |
| Remote exploit + no auth required | +0.5 | Lower barrier to exploitation |
| Affects credential handling | +1.0 | Credential theft enables further attacks |
| Data exfiltration possible | +0.5 | Confidentiality impact multiplier |
| Persistence mechanism | +1.0 | Attacker can maintain access |
| Supply chain vector | +1.5 | Affects downstream consumers |

## Worked Examples

### Example 1: CWE-22 Path Traversal (PR #752)

**Finding**: `Export-ClaudeMemMemories.ps1:115` - `StartsWith()` without path normalization allows `..` sequences.

| Factor | Value | Notes |
|--------|-------|-------|
| Attack Vector | Local (AV:L) | CLI script, user must run it |
| Attack Complexity | Low (AC:L) | No special conditions |
| Privileges Required | None (PR:N) | Script accepts user input |
| User Interaction | None (UI:N) | Automated exploitation possible |
| Scope | Unchanged (S:U) | Does not escape security boundary |
| Confidentiality | High (C:H) | Can read arbitrary files |
| Integrity | Low (I:L) | Cannot modify directly |
| Availability | None (A:N) | No DoS impact |

**CVSS Calculation**: Base 7.1 (HIGH)

**Context Adjustment**: Local CLI tool, no elevation needed.

**Final Severity**: HIGH (7.1)

**Remediation**: Use `[System.IO.Path]::GetFullPath()` before `StartsWith()` comparison.

### Example 2: CWE-77 Command Injection (PR #752)

**Finding**: `Export-ClaudeMemMemories.ps1:42` - Unquoted variables in npx command allow shell metacharacter injection.

| Factor | Value | Notes |
|--------|-------|-------|
| Attack Vector | Local (AV:L) | CLI script |
| Attack Complexity | Low (AC:L) | Standard injection technique |
| Privileges Required | None (PR:N) | User input controls command |
| User Interaction | None (UI:N) | Automated exploitation |
| Scope | Changed (S:C) | Escapes to OS context |
| Confidentiality | High (C:H) | Full system access |
| Integrity | High (I:H) | Can modify/delete files |
| Availability | High (A:H) | Can crash system |

**CVSS Calculation**: Base 9.8 (CRITICAL)

**Context Adjustment**: None (already CRITICAL).

**Final Severity**: CRITICAL (9.8)

**Remediation**: Quote all variables in external commands: `"$Variable"` not `$Variable`.

### Example 3: CWE-89 SQL Injection (Generic)

**Finding**: API endpoint `/api/search` passes user input directly to SQL query without parameterization.

| Factor | Value | Notes |
|--------|-------|-------|
| Attack Vector | Network (AV:N) | Remote API |
| Attack Complexity | Low (AC:L) | Standard SQLi techniques |
| Privileges Required | None (PR:N) | Public endpoint |
| User Interaction | None (UI:N) | Automated exploitation |
| Scope | Changed (S:C) | Database access beyond app |
| Confidentiality | High (C:H) | Full database dump |
| Integrity | High (I:H) | Data modification |
| Availability | High (A:H) | DROP TABLE possible |

**CVSS Calculation**: Base 9.8 (CRITICAL)

**Context Adjustment**: Remote service + no auth = +0.5 (capped at 10.0).

**Final Severity**: CRITICAL (10.0)

**Remediation**: Use parameterized queries exclusively.

### Example 4: CWE-20 Missing Input Validation

**Finding**: PowerShell function accepts `$Path` parameter without validation, passes to `Get-Content`.

| Factor | Value | Notes |
|--------|-------|-------|
| Attack Vector | Local (AV:L) | CLI function |
| Attack Complexity | High (AC:H) | Requires specific conditions |
| Privileges Required | Low (PR:L) | Must be calling code |
| User Interaction | Required (UI:R) | User must invoke function |
| Scope | Unchanged (S:U) | Stays within script context |
| Confidentiality | Low (C:L) | Limited info disclosure |
| Integrity | None (I:N) | Read-only operation |
| Availability | None (A:N) | No DoS impact |

**CVSS Calculation**: Base 2.5 (LOW)

**Context Adjustment**: None (local CLI).

**Final Severity**: LOW (2.5)

**Remediation**: Add `[ValidateScript()]` attribute to `$Path` parameter.

### Example 5: CWE-798 Hardcoded Credentials

**Finding**: `config.ps1` contains `$ApiKey = "sk-proj-abc123..."` hardcoded.

| Factor | Value | Notes |
|--------|-------|-------|
| Attack Vector | Local (AV:L) | Source code access needed |
| Attack Complexity | Low (AC:L) | Plaintext credentials |
| Privileges Required | None (PR:N) | Any repo access |
| User Interaction | None (UI:N) | Automated extraction |
| Scope | Changed (S:C) | Enables external API abuse |
| Confidentiality | High (C:H) | Full API access |
| Integrity | High (I:H) | Can modify API state |
| Availability | Low (A:L) | Rate limit exhaustion |

**CVSS Calculation**: Base 7.5 (HIGH)

**Context Adjustment**: Remote service (API key enables remote access) = +1.5.

**Final Severity**: CRITICAL (9.0)

**Remediation**: Move credentials to environment variables or secure vault. Rotate compromised key immediately.

## CVSS Calculator Reference

Use the official CVSS v3.1 calculator for precise scoring: [FIRST CVSS Calculator](https://www.first.org/cvss/calculator/3.1)

## Severity Overrides

Security agent may override calculated severity with documented justification:

| Override | When to Use | Documentation Required |
|----------|-------------|------------------------|
| Upgrade to CRITICAL | Known active exploitation | CVE reference or threat intel |
| Upgrade to CRITICAL | Affects authentication/authorization | Blast radius analysis |
| Downgrade one level | Defense-in-depth mitigates | Specific control documentation |
| Downgrade one level | Requires improbable conditions | Attack chain analysis |

## AI Agent CVSS Alignment

For AI/ML-specific vulnerabilities (OWASP Agentic Top 10), apply AIVSS modifiers:

| AI Factor | Modifier | Applies To |
|-----------|----------|------------|
| Autonomous execution | +1.0 | ASI05, ASI08 |
| Cross-session persistence | +0.5 | ASI06, ASI10 |
| Human bypass | +1.5 | ASI01, ASI09 |
| Supply chain propagation | +2.0 | ASI04 |

## References

- [CVSS v3.1 Specification](https://www.first.org/cvss/specification-document)
- [CWE-699 Software Development View](https://cwe.mitre.org/data/definitions/699.html)
- [OWASP Top 10 for Agentic Applications](https://genai.owasp.org/)
- [PR #752 Security RCA](/.agents/analysis/security-agent-failure-rca.md)
- [Issue #755 Security Agent Failure Tracking](https://github.com/rjmurillo/ai-agents/issues/755)
