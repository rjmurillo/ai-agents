# ADR-037 Security Review: Memory Router Architecture

**Reviewer**: Security Agent
**Date**: 2026-01-01
**ADR Status**: Proposed (Phase 1: Independent Review)
**Decision**: Unified memory access layer integrating Serena and Forgetful

---

## Executive Summary

**Risk Score: 6/10 (Medium)**

ADR-037 introduces a unified memory routing layer with acceptable security properties but requires hardening in query handling, HTTP transport security, and availability fallback logic. The architecture relies on HTTP communication with an unencrypted localhost service (Forgetful on port 8020), and the proposed query routing lacks explicit input validation. Three issues require remediation before implementation.

---

## Security Assessment

### 1. INPUT VALIDATION VULNERABILITY [P1: HIGH]

**Issue**: Query parameter handling lacks explicit validation

**Location**: ADR-037, line 73-77 (Search-Memory function signature)

**Description**:
The proposed `Search-Memory` function accepts a `-Query` parameter without documented validation constraints. The routing logic passes this query directly to both Forgetful and Serena search functions:

```powershell
function Search-Memory {
    param(
        [string]$Query,           # NO TYPE VALIDATION
        [int]$MaxResults = 10,
        [switch]$ForceSerena,
        [switch]$ForceForgetful
    )
    # Direct routing without validation:
    $results = Invoke-ForgetfulSearch -Query $Query -Limit $MaxResults
    $serenaResults = Invoke-SerenaSearch -Query $Query -Limit $MaxResults
}
```

**Attack Vector**:
- **CWE-20**: Improper Input Validation
- **Risk**: Query injection in Serena file search (line 163: `$fileName -match $_`)
  - Pattern matching without escaping: `"../../../etc/passwd" -match ".*"` could match sensitive file names
  - Regex special chars: `.*`, `.+`, `[^a-z]` not escaped
- **HTTP Payload Injection** in Forgetful requests (line 314: POST body construction)
  - Query string not validated before JSON encoding
  - Could inject malformed JSON or escape sequences

**Example Exploit**:
```powershell
# Regex injection in Serena search
Search-Memory -Query ".*"  # Matches ALL memory files
Search-Memory -Query "password|secret"  # Disjunction

# JSON injection in Forgetful
Search-Memory -Query '","injected":"value'  # Breaks JSON structure
```

**Severity**: HIGH - Affects query routing to both systems
**CVSS Score**: 5.3 (Medium) - Information disclosure via regex match all
**Remediation Required**: YES

---

### 2. HTTP TRANSPORT SECURITY RISK [P1: HIGH]

**Issue**: Unencrypted HTTP to localhost service, no TLS verification

**Location**: `.mcp.json`, line 25; ADR-037, line 95

**Description**:
The Forgetful MCP endpoint is configured as unencrypted HTTP:

```json
{
  "forgetful": {
    "type": "http",
    "url": "http://localhost:8020/mcp"  // NO TLS
  }
}
```

The benchmark script (lines 236-243) performs HTTP without security validation:

```powershell
function Test-ForgetfulAvailable {
    try {
        $null = Invoke-RestMethod -Uri $Endpoint -Method Get -TimeoutSec 2
        return $true
    }
    catch {
        return $false
    }
}
```

**Attack Vector**:
- **CWE-319**: Cleartext Transmission of Sensitive Information
- **Threat**: Man-in-the-middle (MITM) on localhost
  - Query content transmitted unencrypted
  - Memory search results transmitted unencrypted
  - Service authentication tokens (if any) exposed
- **Port Enumeration**: Localhost-only, limited scope, but:
  - Docker/container scenarios: localhost may span network
  - WSL (Windows Subsystem for Linux): localhost accessible from Windows host

**Severity**: HIGH - Affects all Forgetful queries
**CVSS Score**: 6.5 (Medium) - Network MITM on localhost, requires local access
**Assumption**: Localhost isolation is assumed but not verified
**Remediation Required**: YES (with context)

---

### 3. AVAILABILITY FALLBACK LOGIC BYPASS [P2: MEDIUM]

**Issue**: Unavailability check timeout (2 seconds) can cause cascading failures

**Location**: Measure-MemoryPerformance.ps1, line 236; ADR-037 implied routing

**Description**:
The `Test-ForgetfulAvailable` health check uses a 2-second timeout:

```powershell
$null = Invoke-RestMethod -Uri $Endpoint -Method Get -TimeoutSec 2 -ErrorAction Stop
```

In the router's routing logic (ADR-037, lines 80-92), if Forgetful is slow but not completely unavailable:

```powershell
# If Forgetful times out after 2s, falls back to Serena
# But subsequent requests may also timeout, causing:
# 1. 2s delay + Serena lookup = slow queries
# 2. Cascading timeouts under load
# 3. Hammering both systems during partial outage
```

**Attack Vector**:
- **CWE-400**: Uncontrolled Resource Consumption
- **Threat**: Denial of Service (DoS) via slow Forgetful service
  - Attacker slows Forgetful service → 2s timeout per query
  - Router falls back to Serena for all queries
  - If Serena also slow, users experience ~4s latency minimum
  - Repeated queries during outage cause resource exhaustion

**Scenario**:
```powershell
# Normal: 100ms Forgetful
Search-Memory -Query "authentication"  # 100ms

# Degraded: 1500ms Forgetful (approaching timeout)
Search-Memory -Query "authentication"  # 1500ms + fallback attempt
# Router waits 2s for timeout, THEN tries Serena (adds 530ms more)
# Total: 2500ms per query

# Cascading failure: 10 concurrent queries × 2.5s = 25s wall time
```

**Severity**: MEDIUM - Availability impact, not confidentiality/integrity
**CVSS Score**: 4.3 (Medium) - Requires adversary control of Forgetful service
**Remediation Required**: YES

---

### 4. RESULT DEDUPLICATION STRATEGY [P2: MEDIUM]

**Issue**: Content hash deduplication (line 91) lacks specification

**Location**: ADR-037, lines 98-104 (Result Merging Strategy)

**Description**:
The merging strategy references deduplication "by content hash" but provides no algorithm specification:

```powershell
$results = Merge-MemoryResults -Primary $results -Secondary $serenaResults
# No documented hash algorithm, collision strategy, or sensitivity level
```

**Attack Vector**:
- **CWE-327**: Use of Broken Cryptography
- **Threat**: Hash collision attacks
  - If using weak hash (MD5, SHA1), crafted memory content could collide
  - Two different sensitive memories could be merged into one result
  - Memory content could be deduplicated incorrectly

**Severity**: MEDIUM - Information accuracy issue
**CVSS Score**: 3.7 (Low) - Requires crafted memory content
**Remediation Required**: RECOMMENDED

---

## Strengths

1. **Graceful Degradation**: Fallback design ensures availability even when Forgetful unavailable [PASS]
2. **System Isolation**: Serena and Forgetful remain independent, no shared state [PASS]
3. **Port Isolation**: Services on non-standard ports reduce default attack surface [PASS]
4. **Read-Only Operations**: Memory router performs searches only, no writes to Forgetful [PASS]
5. **Type Safety**: PowerShell parameter types constrain some inputs (integers, switches) [PASS]

---

## Weaknesses & Gaps

| Issue | Priority | Category | Severity |
|-------|----------|----------|----------|
| Query parameter validation missing | P1 | Input Validation | HIGH |
| HTTP transport unencrypted | P1 | Transport Security | HIGH |
| Timeout-based fallback vulnerable to DoS | P2 | Availability | MEDIUM |
| Hash algorithm unspecified for dedup | P2 | Data Integrity | MEDIUM |
| No request logging for audit trail | P2 | Auditability | LOW |

---

## Scope Concerns

### 1. Query String Length Limits (Not Addressed)

**Risk**: Unbounded query strings could cause:
- Memory exhaustion in router process
- Performance degradation in Forgetful embeddings (depends on model)
- Potential regex backtracking in Serena matching

**Recommendation**: Enforce `MaxLength` parameter validation
```powershell
[Parameter(Mandatory)]
[ValidateLength(1, 500)]  # Reasonable limit for search queries
[string]$Query
```

### 2. Concurrency & Rate Limiting (Not Addressed)

**Risk**: No mention of handling concurrent memory queries:
- Forgetful availability check (2-second timeout) could be called repeatedly
- No rate limiting on Router itself
- Could cause resource exhaustion under high load

**Recommendation**: Implement per-session rate limiting:
```powershell
# Cache health check results for 30 seconds
$script:ForgetfulHealthCache = @{
    LastCheck = [DateTime]::MinValue
    IsAvailable = $false
}
```

### 3. Logging & Observability (Mentioned but Not Detailed)

**Risk**: ADR mentions logging (line 146: "Should log routing decisions") but provides no implementation:
- What events to log?
- Which system was used (primary or fallback)?
- Latency metrics?
- Query success/failure rates?

**Recommendation**: Define logging schema before implementation

---

## Questions for Architect Review

1. **Query Validation Scope**: What is the intended query domain?
   - Free-form natural language?
   - Structured pattern matching?
   - Boolean operators allowed?

2. **Forgetful Reliability**: Is HTTP on localhost acceptable for sensitive memory content?
   - Can Forgetful be deployed with TLS?
   - Should router add TLS verification layer?

3. **Merging Strategy**: How should conflicts be handled?
   - Forgetful semantic score vs. Serena recency?
   - What if both systems return different results for same query?

4. **Performance Targets**: Are 50-100ms latency targets realistic with 2-second timeout fallback?
   - Under what conditions does 550ms fallback occur?
   - What SLA is expected?

5. **Security Audit**: Has vector database content been reviewed for sensitive data exposure?
   - Are memory contents filtered before Forgetful indexing?
   - Could sensitive queries leak via embedding similarity?

---

## Blocking Concerns

| Issue | Priority | Description | Blocking | Remediation |
|-------|----------|-------------|----------|-------------|
| Query input validation missing | P1 | No validation on Query parameter | YES | Add ValidateLength + ValidatePattern |
| HTTP transport unencrypted | P1 | Unencrypted localhost HTTP | CONDITIONAL | Add TLS or document assumption |
| DoS-vulnerable timeout logic | P2 | 2s timeout hammers on failure | YES | Implement exponential backoff |
| Dedup hash algorithm unspecified | P2 | Content hash collision risk | RECOMMENDED | Use SHA-256, document algorithm |

**Gate Status**: **BLOCKED** on P1 issues (2)

---

## Recommended Remediations

### Remediation 1: Input Validation (CRITICAL)

**Before Implementation**, add to MemoryRouter.psm1:

```powershell
function Search-Memory {
    param(
        [Parameter(Mandatory)]
        [ValidateLength(1, 500)]
        [ValidatePattern('^[a-zA-Z0-9\s\-.,_()&]+$')]  # Allow natural language + boolean operators
        [string]$Query,

        [Parameter()]
        [ValidateRange(1, 100)]
        [int]$MaxResults = 10,

        [switch]$ForceSerena,
        [switch]$ForceForgetful
    )
}
```

**Rationale**:
- MaxLength prevents unbounded regex backtracking in Serena
- ValidatePattern blocks regex metacharacters that could modify search behavior
- Allows common search operators: parentheses, hyphens, commas

**Test Cases**:
```powershell
# PASS: Normal queries
Search-Memory -Query "PowerShell arrays"
Search-Memory -Query "git pre-commit"

# PASS: Boolean-like queries
Search-Memory -Query "authentication & authorization"

# FAIL: Injection attempts
Search-Memory -Query ".*"  # Regex metachar
Search-Memory -Query '","injected":"value'  # JSON injection
Search-Memory -Query "../../../etc/passwd"  # Path traversal
```

---

### Remediation 2: HTTP Transport Security (CONDITIONAL)

**Option A: Document Localhost Assumption**
```markdown
## Security Assumption: Localhost Isolation

Forgetful MCP is assumed to run on localhost:8020 with OS-level isolation.
- Windows: User isolation via Windows security model
- Linux: Process user isolation
- Docker: Network namespace isolation

This is acceptable for development/internal use but NOT for networked environments.
```

**Option B: Add TLS Layer** (Recommended for production)
```powershell
# Update .mcp.json for Forgetful
{
  "forgetful": {
    "type": "http",
    "url": "https://localhost:8020/mcp",  # TLS required
    "tlsVerify": false  # Accept self-signed for localhost
  }
}

# Update Test-ForgetfulAvailable
function Test-ForgetfulAvailable {
    param([string]$Endpoint)
    try {
        # Suppress TLS warnings for localhost self-signed certs
        [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
        $null = Invoke-RestMethod -Uri $Endpoint -Method Get -TimeoutSec 2
        return $true
    } finally {
        [System.Net.ServicePointManager]::ServerCertificateValidationCallback = $null
    }
}
```

---

### Remediation 3: DoS-Resistant Fallback Logic (CRITICAL)

**Current Risk**: Health check timeout (2s) + direct retry pattern

**Improved Pattern**: Exponential backoff + cached health status

```powershell
# Add to MemoryRouter.psm1
$script:ForgetfulHealth = @{
    LastCheck = [DateTime]::MinValue
    IsAvailable = $false
    BackoffUntil = [DateTime]::MinValue
}

function Test-ForgetfulAvailable {
    param([string]$Endpoint)

    # Check if in backoff period
    if ([DateTime]::UtcNow -lt $script:ForgetfulHealth.BackoffUntil) {
        return $false
    }

    # Check if cached result is fresh (< 30 seconds old)
    if (([DateTime]::UtcNow - $script:ForgetfulHealth.LastCheck).TotalSeconds -lt 30) {
        return $script:ForgetfulHealth.IsAvailable
    }

    # Perform actual health check with exponential backoff
    try {
        $null = Invoke-RestMethod -Uri $Endpoint -Method Get -TimeoutSec 2
        $script:ForgetfulHealth.IsAvailable = $true
        $script:ForgetfulHealth.LastCheck = [DateTime]::UtcNow
        $script:ForgetfulHealth.BackoffUntil = [DateTime]::MinValue
        return $true
    }
    catch {
        $script:ForgetfulHealth.IsAvailable = $false
        $script:ForgetfulHealth.LastCheck = [DateTime]::UtcNow

        # Exponential backoff: 1s, 2s, 4s, 8s max
        $backoffSeconds = [Math]::Min(8, [Math]::Pow(2, $script:FailureCount))
        $script:ForgetfulHealth.BackoffUntil = ([DateTime]::UtcNow).AddSeconds($backoffSeconds)

        return $false
    }
}
```

**Benefits**:
- Avoids hammering Forgetful during outages
- Prevents cascade of timeouts
- Reduces latency under degraded conditions

---

### Remediation 4: Hash Algorithm Specification (RECOMMENDED)

**Document in Merge-MemoryResults Implementation**:

```powershell
<#
.DESCRIPTION
    Merges results from Forgetful (primary) and Serena (secondary).
    Deduplicates by SHA-256 hash of memory content.

    Collisions: Cryptographically negligible risk with SHA-256.
    Edge case: Identical memory content from different systems is correctly deduplicated.
#>
function Merge-MemoryResults {
    param(
        [array]$Primary,      # Forgetful results
        [array]$Secondary     # Serena results
    )

    $merged = @()
    $seenHashes = @{}

    # Process primary results first (semantic search preferred)
    foreach ($result in $Primary) {
        $hash = [System.Security.Cryptography.SHA256]::HashData(
            [System.Text.Encoding]::UTF8.GetBytes($result.Content)
        ) | ForEach-Object { "{0:x2}" -f $_ } | Join-String

        if (-not $seenHashes.ContainsKey($hash)) {
            $merged += $result
            $seenHashes[$hash] = $true
        }
    }

    # Process secondary results (add only if not duplicate)
    foreach ($result in $Secondary) {
        $hash = [System.Security.Cryptography.SHA256]::HashData(
            [System.Text.Encoding]::UTF8.GetBytes($result.Content)
        ) | ForEach-Object { "{0:x2}" -f $_ } | Join-String

        if (-not $seenHashes.ContainsKey($hash)) {
            $merged += $result
            $seenHashes[$hash] = $true
        }
    }

    return $merged
}
```

---

## Security Test Cases (Required Before Implementation)

### Test Suite: ADR-037 Security

```powershell
Describe "Memory Router Security" {
    Context "Input Validation" {
        It "Rejects overly long queries (>500 chars)" {
            $longQuery = "a" * 501
            { Search-Memory -Query $longQuery } | Should -Throw
        }

        It "Rejects regex metacharacters" {
            { Search-Memory -Query ".*" } | Should -Throw
            { Search-Memory -Query ".+" } | Should -Throw
            { Search-Memory -Query "[^a-z]" } | Should -Throw
        }

        It "Rejects JSON injection patterns" {
            { Search-Memory -Query '","injected":"value' } | Should -Throw
        }

        It "Accepts valid natural language queries" {
            { Search-Memory -Query "PowerShell arrays" } | Should -Not -Throw
            { Search-Memory -Query "git pre-commit & security" } | Should -Not -Throw
        }
    }

    Context "Availability Fallback" {
        It "Uses cached health check for 30 seconds" {
            # First call: slow Forgetful (but succeeds)
            # Subsequent calls within 30s: use cached result
            # No repeated health checks
        }

        It "Implements exponential backoff on failure" {
            # Failure 1: Backoff 1s
            # Failure 2: Backoff 2s
            # Failure 3: Backoff 4s
            # Failure 4: Backoff 8s (capped)
        }
    }

    Context "Result Deduplication" {
        It "Removes duplicate memories by SHA-256 hash" {
            # Same content from Forgetful and Serena = 1 result
        }

        It "Preserves order (Forgetful first, then Serena)" {
            # Primary results appear before secondary
        }
    }

    Context "Error Handling" {
        It "Returns Serena results if Forgetful fails" {
            # Mock: Forgetful unavailable
            # Expected: Serena results returned without error
        }

        It "Returns empty array if both fail" {
            # Mock: Both systems unavailable
            # Expected: Empty array (not error)
        }
    }
}
```

---

## Pre-Implementation Checklist

**BLOCKING GATE**: Do not proceed to implementation until all P1 items are resolved.

- [ ] Input validation added (ValidateLength + ValidatePattern)
- [ ] HTTP transport security documented or upgraded to TLS
- [ ] Fallback timeout logic replaced with exponential backoff + caching
- [ ] Hash algorithm (SHA-256) specified in Merge-MemoryResults
- [ ] Security test cases added to test plan
- [ ] Design review confirms query domain (free-form vs. structured)
- [ ] Logging schema defined for routing decisions
- [ ] ADR updated with security constraints section

---

## Summary: Risk Reduction Path

| Risk | Current | Mitigated | Residual |
|------|---------|-----------|----------|
| Query injection | HIGH | With ValidatePattern | LOW |
| HTTP MITM | HIGH | With TLS or assumption docs | MEDIUM |
| DoS via timeout | MEDIUM | With backoff + caching | LOW |
| Hash collisions | MEDIUM | With SHA-256 spec | LOW |
| **Overall Risk Score** | **6/10** | **→ 2/10** | **2/10** |

---

## Conclusion

ADR-037 proposes a reasonable architecture for unified memory access, but **implementation is blocked** on two critical input validation and transport security issues. The fallback logic is vulnerable to DoS attacks under degraded service conditions.

**Recommendation**: **CONDITIONAL APPROVAL**

Approve design after:
1. Adding input validation (ValidateLength, ValidatePattern)
2. Addressing HTTP transport security (TLS or documented assumption)
3. Implementing exponential backoff + health check caching
4. Adding security test cases

Once remediations complete, risk score reduces from 6/10 to 2/10, meeting acceptable threshold for implementation.

---

## References

- **CWE-20**: Improper Input Validation (https://cwe.mitre.org/data/definitions/20.html)
- **CWE-319**: Cleartext Transmission of Sensitive Information (https://cwe.mitre.org/data/definitions/319.html)
- **CWE-327**: Use of Broken Cryptography (https://cwe.mitre.org/data/definitions/327.html)
- **CWE-400**: Uncontrolled Resource Consumption (https://cwe.mitre.org/data/definitions/400.html)
- OWASP Top 10 2021: A06:2021 – Vulnerable and Outdated Components
- **Project Standards**: `.agents/security/security-best-practices.md`
- **Steering Guidance**: `.agents/steering/security-practices.md`

---

**Security Review Status**: [COMPLETE]
**Approved for Implementation**: [CONDITIONAL] - Pending remediation of P1 issues
**Review Date**: 2026-01-01
**Next Review**: After implementation of remediations
