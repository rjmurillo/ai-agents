# Security: Infrastructure File Categories 88

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

## Related

- [security-001-twophase-security-review](security-001-twophase-security-review.md)
- [security-002-input-validation-first-88](security-002-input-validation-first-88.md)
- [security-002-input-validation-first](security-002-input-validation-first.md)
- [security-003-secure-error-handling-90](security-003-secure-error-handling-90.md)
- [security-003-secure-error-handling](security-003-secure-error-handling.md)
