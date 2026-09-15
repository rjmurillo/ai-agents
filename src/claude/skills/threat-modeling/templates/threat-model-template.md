# Threat Model: [System/Feature Name]

**Created**: YYYY-MM-DD
**Version**: 1.0
**Status**: Draft | In Review | Approved
**Author**: [Name]
**Reviewers**: [Names]

---

## 1. Scope

### Subject

[Describe what is being threat modeled]

### Boundaries

**In Scope:**

- [Component 1]
- [Component 2]

**Out of Scope:**

- [Component 3]
- [Third-party service X]

### Stakeholders

| Role | Name | Responsibility |
|------|------|----------------|
| Owner | [Name] | Final approval |
| Security | [Name] | Threat validation |
| Dev Lead | [Name] | Implementation |

---

## 2. Architecture Overview

### Data Flow Diagram

```text
                           Trust Boundary
                      ┌─────────────────────────────┐
                      │                             │
+----------+    HTTPS │   +----------+    SQL       │   +----------+
| Browser  | ─────────┼─> |   API    | ──────────>  │   | Database |
| (User)   | <────────┼── |  Server  | <──────────  │   |          |
+----------+          │   +----------+              │   +----------+
                      │        │                    │
                      │        │ gRPC               │
                      │        v                    │
                      │   +----------+              │
                      │   | Auth     |              │
                      │   | Service  |              │
                      │   +----------+              │
                      │                             │
                      └─────────────────────────────┘
```

### Components

| ID | Name | Type | Description | Owner |
|----|------|------|-------------|-------|
| C001 | Browser | External Entity | User's web browser | N/A |
| C002 | API Server | Process | Main application server | Backend Team |
| C003 | Auth Service | Process | Authentication/authorization | Security Team |
| C004 | Database | Data Store | PostgreSQL database | DBA Team |

### Data Flows

| ID | Source | Destination | Data | Protocol | Auth |
|----|--------|-------------|------|----------|------|
| DF001 | Browser | API Server | User requests | HTTPS | JWT |
| DF002 | API Server | Database | Queries | SQL/TLS | Cert |
| DF003 | API Server | Auth Service | Auth requests | gRPC/mTLS | Cert |

### Trust Boundaries

| ID | Name | Description |
|----|------|-------------|
| TB001 | Internet/DMZ | Traffic from untrusted internet |
| TB002 | Service Mesh | Inter-service communication |

### Assets

| Asset | Classification | Sensitivity |
|-------|----------------|-------------|
| User credentials | Confidential | High |
| Session tokens | Confidential | High |
| User PII | Restricted | Medium |
| Audit logs | Internal | Medium |

---

## 3. STRIDE Analysis

### S - Spoofing

**Definition**: Pretending to be something or someone else

| ID | Element | Threat | Likelihood | Impact | Risk |
|----|---------|--------|------------|--------|------|
| T001 | DF001 | Stolen JWT used to impersonate user | Medium | High | High |
| T002 | C001 | Session hijacking via XSS | Medium | High | High |

### T - Tampering

**Definition**: Modifying data or code without authorization

| ID | Element | Threat | Likelihood | Impact | Risk |
|----|---------|--------|------------|--------|------|
| T003 | DF001 | Man-in-the-middle modifies requests | Low | High | Medium |
| T004 | C004 | SQL injection modifies data | Medium | High | High |

### R - Repudiation

**Definition**: Denying having performed an action

| ID | Element | Threat | Likelihood | Impact | Risk |
|----|---------|--------|------------|--------|------|
| T005 | C002 | User denies making transaction | Medium | Medium | Medium |

### I - Information Disclosure

**Definition**: Exposing information to unauthorized parties

| ID | Element | Threat | Likelihood | Impact | Risk |
|----|---------|--------|------------|--------|------|
| T006 | C002 | Error messages reveal stack traces | High | Medium | High |
| T007 | C004 | Database backup exposed | Low | High | Medium |

### D - Denial of Service

**Definition**: Making a system unavailable or degraded

| ID | Element | Threat | Likelihood | Impact | Risk |
|----|---------|--------|------------|--------|------|
| T008 | C002 | DDoS exhausts server resources | Medium | High | High |
| T009 | DF002 | Connection pool exhaustion | Low | Medium | Low |

### E - Elevation of Privilege

**Definition**: Gaining capabilities without authorization

| ID | Element | Threat | Likelihood | Impact | Risk |
|----|---------|--------|------------|--------|------|
| T010 | C003 | Broken access control bypasses auth | Medium | High | High |
| T011 | C002 | IDOR allows access to other users' data | Medium | High | High |

---

## 4. Threat Matrix Summary

| ID | Element | STRIDE | Threat | Likelihood | Impact | Risk | Status |
|----|---------|--------|--------|------------|--------|------|--------|
| T001 | DF001 | S | Stolen JWT impersonation | Medium | High | High | Mitigating |
| T002 | C001 | S | Session hijacking via XSS | Medium | High | High | Planned |
| T003 | DF001 | T | MITM request modification | Low | High | Medium | Mitigated |
| T004 | C004 | T | SQL injection | Medium | High | High | Mitigating |
| T005 | C002 | R | Transaction repudiation | Medium | Medium | Medium | Planned |
| T006 | C002 | I | Stack trace exposure | High | Medium | High | Mitigating |
| T007 | C004 | I | Backup exposure | Low | High | Medium | Planned |
| T008 | C002 | D | DDoS attack | Medium | High | High | Mitigating |
| T009 | DF002 | D | Connection pool exhaustion | Low | Medium | Low | Accepted |
| T010 | C003 | E | Broken access control | Medium | High | High | Planned |
| T011 | C002 | E | IDOR vulnerability | Medium | High | High | Mitigating |

---

## 5. Mitigations

### Critical/High Priority

#### T001: Stolen JWT Impersonation

**Risk**: High

**Mitigations**:

- [x] Short JWT expiration (15 min)
- [ ] Refresh token rotation
- [ ] Token binding to device fingerprint

**Owner**: Security Team
**Target**: Sprint 24

#### T004: SQL Injection

**Risk**: High

**Mitigations**:

- [x] Parameterized queries
- [x] Input validation
- [ ] WAF rules for SQL patterns

**Owner**: Backend Team
**Target**: Sprint 23

#### T008: DDoS Attack

**Risk**: High

**Mitigations**:

- [x] CDN with DDoS protection
- [ ] Rate limiting per IP
- [ ] Geographic blocking capability

**Owner**: DevOps Team
**Target**: Sprint 24

#### T002: Session Hijacking via XSS

**Risk**: High

**Mitigations**:

- [ ] Content Security Policy headers
- [ ] HttpOnly and Secure cookie flags
- [ ] XSS sanitization library

**Owner**: Frontend Team
**Target**: Sprint 25

#### T003: MITM Request Modification

**Risk**: Medium (after TLS)

**Mitigations**:

- [x] TLS 1.3 enforced
- [x] HSTS headers
- [ ] Certificate pinning (mobile apps)

**Owner**: DevOps Team
**Target**: Completed

#### T006: Stack Trace Exposure

**Risk**: High

**Mitigations**:

- [ ] Custom error pages in production
- [ ] Error logging to secure backend
- [ ] Remove debug mode in production

**Owner**: Backend Team
**Target**: Sprint 24

#### T007: Database Backup Exposure

**Risk**: Medium

**Mitigations**:

- [ ] Encrypted backups at rest
- [ ] Secure backup storage (separate from app)
- [ ] Access control on backup location

**Owner**: DBA Team
**Target**: Sprint 26

#### T010: Broken Access Control

**Risk**: High

**Mitigations**:

- [ ] Centralized authorization middleware
- [ ] Object-level permission checks
- [ ] Security testing for BOLA/IDOR

**Owner**: Backend Team
**Target**: Sprint 25

#### T011: IDOR Vulnerability

**Risk**: High

**Mitigations**:

- [ ] UUID instead of sequential IDs
- [ ] Ownership verification on all endpoints
- [ ] Automated IDOR testing

**Owner**: Backend Team
**Target**: Sprint 25

### Medium Priority

#### T005: Transaction Repudiation

**Mitigations**:

- [ ] Comprehensive audit logging
- [ ] Log integrity protection (signing)
- [ ] Log retention policy

**Owner**: Backend Team
**Target**: Q2 2026

### Accepted Risks

#### T009: Connection Pool Exhaustion

**Justification**: Low likelihood, monitoring in place, auto-scaling handles load spikes.

**Compensating Controls**:

- Database connection monitoring
- Alert on pool saturation >80%
- Automatic recovery procedures

---

## 6. Validation Checklist

- [x] All components identified
- [x] All data flows mapped
- [x] All trust boundaries documented
- [x] All STRIDE categories considered
- [ ] All Critical/High risks have mitigations
- [ ] Peer review completed
- [ ] Stakeholder sign-off

---

## 7. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | YYYY-MM-DD | [Author] | Initial threat model |

---

## 8. References

- [OWASP Threat Modeling](https://owasp.org/www-community/Threat_Modeling)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CWE/SANS Top 25](https://cwe.mitre.org/top25/)
- [Related ADRs: ADR-XXX]
