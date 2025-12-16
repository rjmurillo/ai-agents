# Security Skills

**Extracted**: 2025-12-16
**Source**: `.agents/retrospective/phase1-remediation-pr43.md`

## Skill-Security-001: Two-Phase Security Review

**Statement**: Security review requires TWO phases: pre-implementation (threat model, controls) and post-implementation (verification, actual code review)

**Context**: Any feature with security implications

**Evidence**: Issue #I7 - security script not re-reviewed after implementation; implementer is best positioned to flag security-relevant changes during coding

**Atomicity**: 94%

**Tag**: helpful

**Impact**: 10/10

**Pattern**:

```text
Phase 1 (Pre-Implementation):
  security agent → Threat model, required controls, security requirements
  
Phase 2 (Implementation):  
  implementer → Code + flag security-relevant changes for review
  
Phase 3 (Post-Implementation):
  security agent → Verify controls implemented, actual code review
```

**Anti-Pattern**:

- Single security review at planning time only
- Security not re-engaged after implementation
- No handoff from implementer back to security

---

---

## Skill-Security-002: Input Validation First (88%)

**Statement**: Always validate and sanitize inputs before processing

**Context**: Any code handling external data

**Evidence**: Security best practices document in governance

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 9/10

**Strategy**:

- Parameterized queries for database access
- Allowlists over denylists for input validation
- Type checking before processing

**Source**: `.agents/security/security-best-practices.md`

---

## Skill-Security-003: Secure Error Handling (90%)

**Statement**: Never expose stack traces or internal details in errors

**Context**: Error handling in any user-facing code

**Evidence**: Security best practices document

**Atomicity**: 90%

**Tag**: helpful

**Impact**: 8/10

**Pattern**:

- Generic messages to external users
- Detailed logs internal only
- Correlation IDs for debugging

**Source**: `.agents/security/security-best-practices.md`

---

## Skill-Security-004: Security Event Logging (85%)

**Statement**: Log security events with context but without sensitive data

**Context**: Authentication, access control, data changes

**Evidence**: Security best practices document

**Atomicity**: 85%

**Tag**: helpful

**Impact**: 8/10

**Events to Log**:

- Authentication attempts (success/failure)
- Authorization decisions
- Data modifications
- Configuration changes

**Source**: `.agents/security/security-best-practices.md`

---

## Skill-Security-005: Regex-Based Secret Detection (92%)

**Statement**: Use regex patterns to detect hardcoded secrets in code

**Context**: Pre-commit hooks, PR gates, security scans

**Evidence**: Secret detection patterns document with regex library

**Atomicity**: 92%

**Tag**: helpful

**Impact**: 9/10

**Pattern Categories**:

- AWS keys: `AKIA[0-9A-Z]{16}`
- GitHub tokens: `gh[ps]_[A-Za-z0-9]{36}`
- Connection strings: `(password|pwd)=[^;]+`
- API keys: `(api_key|apikey)=[A-Za-z0-9]+`

**Source**: `.agents/security/secret-detection-patterns.md`

---

## Skill-Security-006: Infrastructure File Categories (88%)

**Statement**: Target security reviews on 8 categories of security-sensitive files

**Context**: Security review scoping and prioritization

**Evidence**: Infrastructure file patterns document

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 8/10

**Categories**:

1. CI/CD: `*.yml`, `*.yaml` in `.github/`, `.gitlab-ci/`
2. IaC: `*.tf`, `*.tfvars`, `*.bicep`, `*.arm.json`
3. Docker: `Dockerfile*`, `docker-compose*.yml`
4. Kubernetes: `*.yaml` in `k8s/`, `helm/`
5. Scripts: `*.sh`, `*.ps1`, `*.bat`
6. Configs: `*.config`, `*.conf`, `*.ini`
7. Cloud: `*.aws`, `*.azure`, `*.gcp`
8. Network: firewall rules, security groups

**Source**: `.agents/security/infrastructure-file-patterns.md`

---

## Related Documents

- Source: `.agents/retrospective/phase1-remediation-pr43.md`
- Source: `.agents/security/security-best-practices.md`
- Source: `.agents/security/secret-detection-patterns.md`
- Source: `.agents/security/infrastructure-file-patterns.md`
- Issue: #I7 in retrospective
- Related: skills-process-workflow-gaps (workflow patterns)
