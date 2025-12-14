# Infrastructure File Patterns

## Purpose

This document defines file patterns that indicate infrastructure or security-critical code changes. Changes matching these patterns should trigger security agent review.

## Pattern Categories

### Category 1: CI/CD Pipelines (Critical)

| Pattern | Description | Risk Level |
|---------|-------------|------------|
| `.github/workflows/*.yml` | GitHub Actions workflows | Critical |
| `.github/workflows/*.yaml` | GitHub Actions workflows | Critical |
| `.github/actions/**` | Custom GitHub Actions | Critical |
| `azure-pipelines.yml` | Azure DevOps pipelines | Critical |
| `.gitlab-ci.yml` | GitLab CI/CD | Critical |
| `Jenkinsfile` | Jenkins pipeline | Critical |
| `.circleci/**` | CircleCI configuration | Critical |
| `.travis.yml` | Travis CI | Critical |
| `bitbucket-pipelines.yml` | Bitbucket Pipelines | Critical |

### Category 2: Git Hooks (Critical)

| Pattern | Description | Risk Level |
|---------|-------------|------------|
| `.githooks/*` | Custom git hooks | Critical |
| `.husky/*` | Husky hooks | Critical |
| `.git/hooks/*` | Git hooks directory | Critical |
| `.pre-commit-config.yaml` | Pre-commit framework | High |

### Category 3: Build Scripts (High)

| Pattern | Description | Risk Level |
|---------|-------------|------------|
| `build/**/*.ps1` | PowerShell build scripts | High |
| `build/**/*.sh` | Shell build scripts | High |
| `build/**/*.cmd` | Batch scripts | High |
| `build/**/*.bat` | Batch scripts | High |
| `scripts/**/*.ps1` | PowerShell scripts | High |
| `scripts/**/*.sh` | Shell scripts | High |
| `Makefile` | Make build file | High |
| `CMakeLists.txt` | CMake configuration | High |
| `*.cake` | Cake build scripts | High |
| `cake.ps1` | Cake bootstrapper | High |
| `build.ps1` | Build script | High |
| `build.sh` | Build script | High |

### Category 4: Container Configuration (High)

| Pattern | Description | Risk Level |
|---------|-------------|------------|
| `Dockerfile*` | Docker images | High |
| `docker-compose*.yml` | Docker Compose | High |
| `docker-compose*.yaml` | Docker Compose | High |
| `.dockerignore` | Docker ignore file | Medium |
| `*.dockerfile` | Named dockerfiles | High |
| `k8s/**` | Kubernetes manifests | High |
| `kubernetes/**` | Kubernetes manifests | High |
| `helm/**` | Helm charts | High |
| `charts/**` | Helm charts | High |

### Category 5: Authentication/Authorization Code (Critical)

| Pattern | Description | Risk Level |
|---------|-------------|------------|
| `**/Auth/**` | Authentication modules | Critical |
| `**/Authentication/**` | Authentication modules | Critical |
| `**/Authorization/**` | Authorization modules | Critical |
| `**/Security/**` | Security modules | Critical |
| `**/Identity/**` | Identity modules | Critical |
| `**/*Auth*.cs` | Auth-related C# files | Critical |
| `**/*Auth*.ts` | Auth-related TypeScript | Critical |
| `**/*Auth*.js` | Auth-related JavaScript | Critical |
| `**/*Auth*.py` | Auth-related Python | Critical |

### Category 6: API Controllers (High)

| Pattern | Description | Risk Level |
|---------|-------------|------------|
| `**/Controllers/**` | API controllers | High |
| `**/Endpoints/**` | API endpoints | High |
| `**/Handlers/**` | Request handlers | High |
| `**/Middleware/**` | HTTP middleware | High |

### Category 7: Configuration Files (High)

| Pattern | Description | Risk Level |
|---------|-------------|------------|
| `appsettings*.json` | .NET configuration | High |
| `web.config` | IIS configuration | High |
| `app.config` | .NET app config | High |
| `*.env*` | Environment files | Critical |
| `.env.example` | Environment template | Medium |
| `config/*.json` | JSON configs | High |
| `config/*.yml` | YAML configs | High |
| `config/*.yaml` | YAML configs | High |

### Category 8: Infrastructure as Code (High)

| Pattern | Description | Risk Level |
|---------|-------------|------------|
| `*.tf` | Terraform files | High |
| `*.tfvars` | Terraform variables | Critical |
| `terraform/**` | Terraform modules | High |
| `*.bicep` | Azure Bicep | High |
| `*.arm.json` | ARM templates | High |
| `cloudformation/**` | AWS CloudFormation | High |
| `pulumi/**` | Pulumi IaC | High |
| `ansible/**` | Ansible playbooks | High |

### Category 9: Package Management (Medium)

| Pattern | Description | Risk Level |
|---------|-------------|------------|
| `package.json` | npm package | Medium |
| `package-lock.json` | npm lock file | Medium |
| `yarn.lock` | Yarn lock file | Medium |
| `*.csproj` | .NET project file | Medium |
| `*.sln` | .NET solution | Low |
| `requirements.txt` | Python requirements | Medium |
| `Pipfile*` | Python Pipfile | Medium |
| `pyproject.toml` | Python project | Medium |
| `pom.xml` | Maven POM | Medium |
| `build.gradle*` | Gradle build | Medium |
| `go.mod` | Go modules | Medium |
| `Cargo.toml` | Rust Cargo | Medium |
| `Gemfile*` | Ruby gems | Medium |
| `nuget.config` | NuGet configuration | High |
| `.npmrc` | npm configuration | High |
| `.yarnrc*` | Yarn configuration | High |

### Category 10: Secrets and Certificates (Critical)

| Pattern | Description | Risk Level |
|---------|-------------|------------|
| `*.pem` | PEM certificates | Critical |
| `*.key` | Private keys | Critical |
| `*.p12` | PKCS12 files | Critical |
| `*.pfx` | PFX certificates | Critical |
| `*.jks` | Java keystores | Critical |
| `*secret*` | Secret files | Critical |
| `*credential*` | Credential files | Critical |
| `*password*` | Password files | Critical |

## Risk Level Definitions

| Level | Definition | Action Required |
|-------|------------|-----------------|
| Critical | Immediate security implications | Security agent review REQUIRED |
| High | Potential security impact | Security agent review RECOMMENDED |
| Medium | Indirect security impact | Security agent review OPTIONAL |
| Low | Minimal security concern | No automatic trigger |

## Detection Algorithm

```python
def should_trigger_security_review(changed_files):
    """
    Determine if security agent review should be triggered.
    Returns: (should_trigger, risk_level, matching_patterns)
    """
    critical_patterns = [
        ".github/workflows/*",
        ".githooks/*",
        "**/Auth/**",
        "**/Security/**",
        "*.env*",
        "*.pem", "*.key", "*.p12", "*.pfx",
        "*secret*", "*credential*"
    ]

    high_patterns = [
        "build/**/*.ps1", "build/**/*.sh",
        "Dockerfile*", "docker-compose*",
        "**/Controllers/**",
        "appsettings*.json",
        "*.tf", "*.tfvars"
    ]

    matches = []
    highest_risk = "none"

    for file in changed_files:
        if matches_any(file, critical_patterns):
            matches.append((file, "critical"))
            highest_risk = "critical"
        elif matches_any(file, high_patterns):
            matches.append((file, "high"))
            if highest_risk != "critical":
                highest_risk = "high"

    should_trigger = highest_risk in ["critical", "high"]
    return (should_trigger, highest_risk, matches)
```

## Integration Points

### Pre-commit Hook

Calls detection script, displays warning if matches found.

### PR Template

Includes checkbox for security review when patterns match.

### Orchestrator Routing

Uses patterns to auto-include security agent in routing.

## Related Documents

- [Static Analysis Checklist](./static-analysis-checklist.md)
- [Security Best Practices](./security-best-practices.md)
- [Orchestrator Routing Algorithm](../../docs/orchestrator-routing-algorithm.md)

---

*Document Version: 1.0*
*Created: 2025-12-13*
*GitHub Issue: #9*
