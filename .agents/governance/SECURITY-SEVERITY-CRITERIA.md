# Security Severity Calibration Criteria

> **Status**: Canonical Source of Truth for security severity classification

## Purpose

Provides CVSS v3.1-based severity calibration for consistent security vulnerability classification across security agent reviews, threat modeling, and post-implementation verification.

## CVSS v3.1 Base Score Thresholds

| Severity | CVSS Score Range | Description |
|----------|------------------|-------------|
| **CRITICAL** | 9.0 - 10.0 | Allows complete system compromise, data exfiltration, or widespread impact |
| **HIGH** | 7.0 - 8.9 | Significant security boundary violation, privileged access, or data breach risk |
| **MEDIUM** | 4.0 - 6.9 | Moderate security impact, requires additional conditions to exploit |
| **LOW** | 0.1 - 3.9 | Minor security concern, limited impact, or defense-in-depth violation |

**Reference**: CVSS v3.1 Calculator - <https://www.first.org/cvss/calculator/3.1>

## Threat Actor Context Modifiers

Security severity MUST account for threat actor capability and attack surface. Local CLI tools have different threat models than remote services.

### Context Matrix

| Threat Actor / Severity | CRITICAL (9.0-10.0) | HIGH (7.0-8.9) | MEDIUM (4.0-6.9) | LOW (0.1-3.9) |
|-------------------------|---------------------|----------------|------------------|---------------|
| **Local CLI (Trusted Environment)** | Privilege escalation, credential theft, code execution | Data exfiltration, unauthorized file access | Input validation bypass, ReDoS | Information disclosure, weak crypto |
| **Remote Service (Untrusted Network)** | RCE, SQL injection, authentication bypass | Authorization bypass, XSS, CSRF | Verbose errors, weak session management | Security misconfiguration |

**Key Distinctions**:

- **Local CLI**: Assumes attacker has physical/SSH access, focuses on privilege escalation and lateral movement
- **Remote Service**: Assumes untrusted network input, focuses on injection and authentication/authorization failures

## Severity Elevation Criteria

Base CVSS score may be elevated based on deployment context:

| Condition | Elevation | Reasoning |
|-----------|-----------|-----------|
| **Local exploit + privileged execution** | +2.0 | Turns MEDIUM (5.0) into CRITICAL (7.0+) - escalation to admin/root |
| **Remote exploit + no authentication required** | +0.5 | Increases likelihood and impact (unauthenticated attack surface) |
| **Affects multiple components** | +1.0 | Cascading failure risk (OWASP ASI08) |
| **Credential exposure in logs/errors** | +1.5 | Enables secondary attacks (lateral movement, data breach) |
| **Bypass of security control** | +1.0 | Undermines defense-in-depth architecture |

**Example**: CWE-22 path traversal in local CLI script:

- Base CVSS: 7.5 (HIGH)
- Context: Local CLI with privileged execution
- Elevation: +2.0 (privilege escalation)
- **Final Severity**: 9.5 (CRITICAL)

## Worked Examples from PR #752

### Example 1: CWE-22 Path Traversal (Export-ClaudeMemMemories.ps1)

**Vulnerability**: `StartsWith()` without path normalization allows `..` sequences to escape allowed directory

```powershell
# VULNERABLE CODE
if (-not $OutputFile.StartsWith($MemoriesDir)) {
    Write-Warning "Output file should be in $MemoriesDir"
}
# WARNING ONLY - Attacker can write to arbitrary paths
```

**CVSS v3.1 Calculation**:

- **Attack Vector (AV)**: Local (L) - requires CLI access
- **Attack Complexity (AC)**: Low (L) - trivial to exploit with `../../etc/passwd`
- **Privileges Required (PR)**: Low (L) - standard user can run script
- **User Interaction (UI)**: None (N) - automated via parameter
- **Scope (S)**: Changed (C) - escapes intended directory boundary
- **Confidentiality (C)**: High (H) - read arbitrary files
- **Integrity (I)**: High (H) - write arbitrary files
- **Availability (A)**: Low (L) - can overwrite critical files

**Base Score**: 7.8 (HIGH)

**Context Adjustment**:

- Local CLI environment: Standard threat model for developer tools
- Privileged execution possible: Script may run with admin rights during setup
- Credential theft risk: Can write to `~/.ssh/`, `.aws/credentials`

**Elevation**: +2.0 (privilege escalation potential)

**Final Severity**: **9.8 (CRITICAL)**

**Justification**: Path traversal in privileged local script enables credential theft and lateral movement, warranting CRITICAL classification despite local-only attack vector.

---

### Example 2: CWE-77 Command Injection (Export-ClaudeMemMemories.ps1)

**Vulnerability**: Unquoted variables in external command allow shell metacharacter injection

```powershell
# VULNERABLE CODE
npx tsx $PluginScript $Query $OutputFile
# Attacker controls $Query or $OutputFile
```

**Attack Example**: `$Query = "; rm -rf /"`

**CVSS v3.1 Calculation**:

- **Attack Vector (AV)**: Local (L) - requires CLI access
- **Attack Complexity (AC)**: Low (L) - trivial to inject via parameter
- **Privileges Required (PR)**: Low (L) - standard user
- **User Interaction (UI)**: None (N) - automated via parameter
- **Scope (S)**: Changed (C) - arbitrary command execution
- **Confidentiality (C)**: High (H) - full file system access
- **Integrity (I)**: High (H) - arbitrary file modification/deletion
- **Availability (A)**: High (H) - can destroy system via `rm -rf`

**Base Score**: 8.8 (HIGH)

**Context Adjustment**:

- Local CLI environment: Standard threat model
- Privileged execution likely: Memory management scripts often run with elevated rights
- Full system compromise: Can execute any command with user's privileges

**Elevation**: +1.0 (complete system compromise potential)

**Final Severity**: **9.8 (CRITICAL)**

**Justification**: Command injection in local script provides complete command execution capability, enabling data exfiltration, credential theft, and system destruction.

---

### Example 3: CWE-89 SQL Injection (Hypothetical Remote API)

**Vulnerability**: String concatenation in SQL query construction

```csharp
// VULNERABLE CODE
string query = "SELECT * FROM users WHERE username = '" + userInput + "'";
```

**CVSS v3.1 Calculation**:

- **Attack Vector (AV)**: Network (N) - remote API endpoint
- **Attack Complexity (AC)**: Low (L) - standard SQL injection technique
- **Privileges Required (PR)**: None (N) - unauthenticated endpoint
- **User Interaction (UI)**: None (N) - automated attack
- **Scope (S)**: Changed (C) - database access beyond application scope
- **Confidentiality (C)**: High (H) - full database read access
- **Integrity (I)**: High (H) - data modification via `UPDATE`/`DELETE`
- **Availability (A)**: High (H) - can drop tables or crash database

**Base Score**: 9.8 (CRITICAL)

**Context Adjustment**:

- Remote service: Untrusted network input
- No authentication required: Widens attack surface
- Multi-tenant impact: One tenant can access others' data

**Elevation**: +0.2 (rounds to CRITICAL ceiling)

**Final Severity**: **10.0 (CRITICAL)**

**Justification**: Unauthenticated remote SQL injection with multi-tenant impact warrants maximum severity.

---

### Example 4: CWE-20 Missing Input Validation (Local CLI)

**Vulnerability**: Missing length validation on string parameter

```powershell
# VULNERABLE CODE
param([string]$Message)
Write-Host "Message: $Message"
# No length limit, allows large inputs
```

**CVSS v3.1 Calculation**:

- **Attack Vector (AV)**: Local (L) - CLI parameter
- **Attack Complexity (AC)**: Low (L) - trivial to provide large input
- **Privileges Required (PR)**: Low (L) - standard user
- **User Interaction (UI)**: None (N) - automated via parameter
- **Scope (S)**: Unchanged (U) - limited to current process
- **Confidentiality (C)**: None (N) - no data exposure
- **Integrity (I)**: None (N) - no data modification
- **Availability (A)**: Low (L) - may cause memory issues with extremely large input

**Base Score**: 3.3 (LOW)

**Context Adjustment**:

- Local CLI environment: Limited threat model
- No privilege escalation: Affects only current process
- Self-inflicted DoS: User would harm their own session

**Elevation**: None

**Final Severity**: **3.3 (LOW)**

**Justification**: Missing input validation in local CLI with no privilege escalation remains LOW severity. Recommend adding validation as defense-in-depth, not as critical fix.

---

### Example 5: CWE-798 Hardcoded Credentials (Remote API)

**Vulnerability**: API key embedded in source code

```csharp
// VULNERABLE CODE
string apiKey = "sk-1234567890abcdef";
var client = new ApiClient(apiKey);
```

**CVSS v3.1 Calculation**:

- **Attack Vector (AV)**: Network (N) - API key usable remotely
- **Attack Complexity (AC)**: Low (L) - key is plaintext in code
- **Privileges Required (PR)**: None (N) - anyone with code access
- **User Interaction (UI)**: None (N) - automated attack
- **Scope (S)**: Changed (C) - compromises external API access
- **Confidentiality (C)**: High (H) - API provides data access
- **Integrity (I)**: High (H) - API allows data modification
- **Availability (A)**: Low (L) - API rate limits prevent full DoS

**Base Score**: 8.6 (HIGH)

**Context Adjustment**:

- Remote service: API key usable from anywhere
- Code in public repository: Widely discoverable
- Third-party API compromise: Affects vendor relationship

**Elevation**: +0.5 (public exposure increases likelihood)

**Final Severity**: **9.1 (CRITICAL)**

**Justification**: Hardcoded credentials for remote API in public repository enables unauthorized access and data breach, warranting CRITICAL classification.

---

## Severity Assignment Process

Follow this checklist when assigning severity to security findings:

1. **Calculate Base CVSS Score**
   - Use CVSS v3.1 Calculator: <https://www.first.org/cvss/calculator/3.1>
   - Document metric selections (AV, AC, PR, UI, S, C, I, A)

2. **Apply Threat Actor Context**
   - Identify attack vector: Local CLI vs Remote Service
   - Assess attacker capability: Physical access, network access, authentication
   - Consider deployment environment: Developer workstation, production server, CI/CD

3. **Apply Elevation Criteria**
   - Check for privilege escalation potential
   - Check for credential exposure risk
   - Check for cascading failure impact
   - Check for security control bypass

4. **Determine Final Severity**
   - Base Score + Elevation = Final Score
   - Map Final Score to severity band (CRITICAL/HIGH/MEDIUM/LOW)
   - Document reasoning in security report

5. **Validate Classification**
   - Compare with similar vulnerabilities in codebase history
   - Review with security team if boundary case (e.g., 6.9 vs 7.0)
   - Document any deviations from standard criteria

## Anti-Patterns to Avoid

| Anti-Pattern | Why It's Wrong | Correct Approach |
|--------------|----------------|------------------|
| **"Trusted environment" severity discount** | Local CLI tools often run with elevated privileges and handle sensitive data | Use threat actor context, but don't automatically downgrade severity for local tools |
| **"It requires user interaction" discount** | Automation, CI/CD, and developer workflows minimize user interaction | Assess actual usage patterns, not theoretical interaction requirements |
| **"External review found it" severity inflation** | Severity is based on impact, not discovery method | Calculate CVSS based on vulnerability characteristics, not who found it |
| **Ignoring cascading impact** | Single vulnerability may enable multi-stage attacks | Consider full attack chain (e.g., path traversal → credential theft → lateral movement) |
| **Assuming input sanitization exists** | Many vulnerabilities occur precisely because sanitization is missing | Base severity on unsanitized input unless validated controls exist |

## References

- **CVSS v3.1 Specification**: <https://www.first.org/cvss/v3.1/specification-document>
- **CVSS v3.1 Calculator**: <https://www.first.org/cvss/calculator/3.1>
- **CWE-699 Software Development View**: <https://cwe.mitre.org/data/definitions/699.html>
- **OWASP Top 10 (2021)**: <https://owasp.org/www-project-top-ten/>
- **OWASP Top 10 for Agentic Applications (2026)**: <https://genai.owasp.org/>
- **NIST NVD Scoring**: <https://nvd.nist.gov/vuln-metrics/cvss>

## Maintenance

This document should be updated when:

- CVSS specification is updated (currently v3.1)
- New threat actor types emerge (e.g., AI-specific threats)
- Organizational risk tolerance changes
- Pattern of severity miscalibration detected across multiple reviews

**Last Updated**: 2026-01-07
**Canonical Source**: `.agents/governance/SECURITY-SEVERITY-CRITERIA.md`
**Related**: `.agents/governance/SECURITY-REVIEW-PROTOCOL.md`, `src/claude/security.md`
