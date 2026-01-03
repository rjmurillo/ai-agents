# ADR-037 Security Findings Summary

**Status**: Phase 1 Independent Review - BLOCKING ISSUES IDENTIFIED
**Risk Score**: 6/10 (Medium) → 2/10 (Low) after remediations
**Approval**: CONDITIONAL - Pending P1 remediation

---

## Critical Findings (P1)

### Finding 1: Query Input Validation Missing

| Attribute | Value |
|-----------|-------|
| **CWE** | CWE-20: Improper Input Validation |
| **CVSS** | 5.3 (Medium) |
| **Risk** | Regex injection in Serena matching, JSON injection in Forgetful |
| **Location** | ADR-037 lines 73-77, Measure-MemoryPerformance.ps1 line 163 |
| **Exploit** | `Search-Memory -Query ".*"` matches all files; `'","injected":"value'` breaks JSON |
| **Severity** | HIGH - Affects routing to both systems |
| **Remediation** | Add ValidateLength(1,500) + ValidatePattern('^[a-zA-Z0-9\s\-.,_()&]+$') |
| **Test** | Reject ".*", accept "PowerShell arrays" |
| **Effort** | 2 hours (validation + tests) |
| **Blocks Implementation** | YES |

---

### Finding 2: HTTP Transport Unencrypted

| Attribute | Value |
|-----------|-------|
| **CWE** | CWE-319: Cleartext Transmission of Sensitive Information |
| **CVSS** | 6.5 (Medium) - localhost only |
| **Risk** | MITM on localhost; query content unencrypted |
| **Location** | .mcp.json line 25, Measure-MemoryPerformance.ps1 line 236 |
| **Threat** | `http://localhost:8020/mcp` without TLS |
| **Severity** | HIGH - All queries affected |
| **Assumption** | Localhost OS-level isolation assumed but not verified |
| **Remediation** | Option A: Document assumption; Option B: Add TLS |
| **Test** | Verify endpoint uses HTTPS or is documented as localhost-only |
| **Effort** | 1-3 hours (docs or TLS setup) |
| **Blocks Implementation** | YES (must document or fix) |

---

## Medium Findings (P2)

### Finding 3: DoS-Vulnerable Timeout Logic

| Attribute | Value |
|-----------|-------|
| **CWE** | CWE-400: Uncontrolled Resource Consumption |
| **CVSS** | 4.3 (Medium) - requires adversary control |
| **Risk** | Cascading timeouts under degraded service conditions |
| **Location** | ADR-037 lines 80-92 (routing logic) |
| **Scenario** | Forgetful slow (1500ms) → 2s timeout → fallback to Serena (530ms) = 2.5s per query |
| **Attack** | Slow Forgetful service, cause repeated timeouts, exhaust resources |
| **Severity** | MEDIUM - Availability impact, not confidentiality |
| **Remediation** | Implement exponential backoff + cache health check (30s TTL) |
| **Test** | Verify no repeated health checks within 30s; backoff: 1s, 2s, 4s, 8s |
| **Effort** | 3 hours (implementation + tests) |
| **Blocks Implementation** | YES |

---

### Finding 4: Dedup Hash Algorithm Unspecified

| Attribute | Value |
|-----------|-------|
| **CWE** | CWE-327: Use of Broken Cryptography |
| **CVSS** | 3.7 (Low) - requires crafted content |
| **Risk** | Hash collision could merge different memories |
| **Location** | ADR-037 line 91 (Merge-MemoryResults) |
| **Issue** | Algorithm not specified: "deduplicate by content hash" |
| **Severity** | MEDIUM - Information accuracy issue |
| **Remediation** | Specify SHA-256 in implementation documentation |
| **Test** | Verify SHA-256 used; no collisions on test data |
| **Effort** | 1 hour (documentation + tests) |
| **Blocks Implementation** | RECOMMENDED (not blocking) |

---

## Additional Concerns (P3: Low Priority)

| Issue | Risk | Recommendation |
|-------|------|-----------------|
| Query length limits (unbounded) | Regex backtracking, memory exhaustion | Add MaxLength validation (remedied by P1) |
| Concurrency & rate limiting | Resource exhaustion under load | Document expected concurrent load; add limits if needed |
| Logging not detailed | Audit trail gaps | Define logging schema (JSON events, latency metrics) |
| No SLA definition | Performance expectations unclear | Document SLA targets and failure modes |
| Forgetful reliability assumption | Service availability risk | Clarify Forgetful deployment expectations |

---

## Remediation Checklist

### Phase 1: Critical Path (Before Implementation)

**P1.1: Input Validation** [BLOCKING]
- [ ] Add `[ValidateLength(1, 500)]` to `-Query` parameter
- [ ] Add `[ValidatePattern('^[a-zA-Z0-9\s\-.,_()&]+$')]` to `-Query`
- [ ] Test: Reject ".*", accept "PowerShell arrays"
- [ ] Test: Reject '","injected":"value'
- [ ] Effort: 2 hours

**P1.2: HTTP Transport Security** [BLOCKING]
- [ ] Option A: Document "Localhost Assumption" section in ADR-037
- [ ] Option B: Update .mcp.json to use HTTPS (tlsVerify=false for self-signed)
- [ ] Update Test-ForgetfulAvailable to suppress TLS warnings
- [ ] Test: Verify endpoint availability check works
- [ ] Effort: 1-3 hours

**P1.3: Fallback Logic Hardening** [BLOCKING]
- [ ] Implement exponential backoff (1s, 2s, 4s, 8s)
- [ ] Add health check caching (30-second TTL)
- [ ] Replace immediate retry with cached result lookup
- [ ] Test: Verify no repeated checks within 30s; backoff timing
- [ ] Effort: 3 hours

**P1.4: Hash Algorithm Specification** [RECOMMENDED]
- [ ] Document SHA-256 in Merge-MemoryResults function
- [ ] Implement SHA-256 content hashing
- [ ] Test: Verify deduplication works correctly
- [ ] Effort: 1 hour

### Phase 2: Optional Hardening (Post-Implementation)

- [ ] Add request logging (query, system used, latency, result count)
- [ ] Implement query length enforcement (via ValidateLength)
- [ ] Add concurrency/rate limiting if needed
- [ ] Define SLA targets and monitoring

---

## Risk Scorecard

### Current State (Proposed Design)

| Risk Category | Finding | CVSS | Blocking | Status |
|---------------|---------|------|----------|--------|
| Input Validation | CWE-20 | 5.3 | YES | ❌ FAIL |
| Transport Security | CWE-319 | 6.5 | YES | ❌ FAIL |
| Availability | CWE-400 | 4.3 | YES | ❌ FAIL |
| Data Integrity | CWE-327 | 3.7 | NO | ⚠️ WARN |
| **Overall** | **6/10** | - | **2 P1** | **BLOCKED** |

### After Remediation

| Risk Category | Finding | CVSS | Mitigated | Status |
|---------------|---------|------|-----------|--------|
| Input Validation | CWE-20 | 5.3 → 1.0 | ValidatePattern | ✅ PASS |
| Transport Security | CWE-319 | 6.5 → 2.0 | TLS or docs | ✅ PASS |
| Availability | CWE-400 | 4.3 → 1.5 | Exponential backoff | ✅ PASS |
| Data Integrity | CWE-327 | 3.7 → 1.0 | SHA-256 spec | ✅ PASS |
| **Overall** | **2/10** | - | **All P1** | **CONDITIONAL APPROVAL** |

---

## Architecture Security Recommendations

### 1. Configuration Hardening

Add to implementation plan:

```powershell
# MemoryRouter.Config.ps1
$MemoryRouterConfig = @{
    QueryMaxLength = 500                    # Prevent unbounded patterns
    MaxResults = 100                        # Limit result set size
    HealthCheckTimeoutSec = 2               # Fail fast on unhealthy
    HealthCheckCacheTtlSec = 30             # Avoid hammering
    BackoffExponent = 2                     # 1, 2, 4, 8 seconds
    BackoffMaxSec = 8                       # Cap exponential growth
    LoggingEnabled = $true                  # Audit trail
}
```

### 2. Logging Schema

```powershell
# Log entry structure for all searches
@{
    Timestamp = Get-Date -Format 'o'
    QueryHash = (Get-Hash -Data $Query)     # Anonymize query content
    SystemUsed = "Forgetful|Serena"         # Which system served request
    LatencyMs = 150                         # Performance metric
    ResultCount = 5                         # Result set size
    Success = $true                         # Success/failure
    Error = $null                           # Error details if failed
}
```

### 3. Timeout & Backoff Strategy

```
Initial Request:
  ├─ Health Check (cached 30s)
  │  ├─ Hit cache? → Skip check
  │  └─ Miss cache? → Call Test-ForgetfulAvailable (2s timeout)
  │
  ├─ Primary (if healthy):
  │  ├─ Forgetful search
  │  └─ Return results
  │
  └─ Fallback (if unhealthy/no results):
     ├─ Serena search
     └─ Return results

On Failure:
  ├─ Failure count++
  ├─ Backoff = 2^failureCount (capped at 8s)
  └─ Skip health checks for backoff duration
```

---

## Testing Requirements

### Security Test Scenarios

```gherkin
Feature: Memory Router Security

Scenario: Reject regex injection attempts
  Given a Memory Router instance
  When I call Search-Memory -Query ".*"
  Then it should throw ValidationException

Scenario: Accept valid natural language
  Given a Memory Router instance
  When I call Search-Memory -Query "PowerShell arrays"
  Then it should return results without error

Scenario: Handle slow Forgetful gracefully
  Given Forgetful service responding in 1500ms
  When I call Search-Memory -Query "test"
  Then it should fallback to Serena after 2s timeout
  And return Serena results

Scenario: Cache health check results
  Given Forgetful is unavailable
  When I call Search-Memory multiple times within 30s
  Then Test-ForgetfulAvailable should be called only once
  And subsequent calls should use cached result

Scenario: Implement exponential backoff
  Given Forgetful is unavailable
  When I call Search-Memory and it fails
  Then backoff timer should be 1s
  And after 1s failure, backoff should be 2s
  And after 3rd failure, backoff should be 4s
```

---

## Sign-Off

| Role | Decision | Date | Notes |
|------|----------|------|-------|
| Security | CONDITIONAL APPROVAL | 2026-01-01 | Pending P1 remediation |
| Architect | PENDING | | Design review required |
| Implementer | BLOCKED | | Cannot proceed until P1 fixed |

---

## References

- **Full Review**: `/home/claude/ai-agents/.agents/security/ADR-037-memory-router-security-review.md`
- **CWE-20**: Improper Input Validation - https://cwe.mitre.org/data/definitions/20.html
- **CWE-319**: Cleartext Transmission - https://cwe.mitre.org/data/definitions/319.html
- **CWE-327**: Use of Broken Cryptography - https://cwe.mitre.org/data/definitions/327.html
- **CWE-400**: Uncontrolled Resource Consumption - https://cwe.mitre.org/data/definitions/400.html
- **Project Security Standards**: `.agents/security/security-best-practices.md`
