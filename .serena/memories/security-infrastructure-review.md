# Security Infrastructure Review

## Skill-Security-006: Infrastructure File Categories (88%)

**Statement**: Target security reviews on 8 categories of security-sensitive files.

**Context**: Security review scoping and prioritization

**Categories**:

| Category | Patterns | Risk Level |
|----------|----------|------------|
| CI/CD | `*.yml`, `*.yaml` in `.github/`, `.gitlab-ci/` | HIGH |
| IaC | `*.tf`, `*.tfvars`, `*.bicep`, `*.arm.json` | HIGH |
| Docker | `Dockerfile*`, `docker-compose*.yml` | HIGH |
| Kubernetes | `*.yaml` in `k8s/`, `helm/` | HIGH |
| Scripts | `*.sh`, `*.ps1`, `*.bat` | MEDIUM |
| Configs | `*.config`, `*.conf`, `*.ini` | MEDIUM |
| Cloud | `*.aws`, `*.azure`, `*.gcp` | HIGH |
| Network | firewall rules, security groups | HIGH |

**Review Priorities**:

```text
1. CI/CD workflows - command injection, secret exposure
2. IaC templates - misconfiguration, public access
3. Dockerfiles - base image vulnerabilities, secrets in layers
4. Scripts - injection, privilege escalation
5. Configs - default credentials, debug settings
```

**Automated Scanning**:

```yaml
# CodeRabbit path_instructions example
"**/.github/workflows/*.yml":
  - "Check for expression injection (${{ }})"
  - "Verify secrets are not logged"
  - "Ensure minimal permissions"
```

**Source**: `.agents/security/infrastructure-file-patterns.md`
