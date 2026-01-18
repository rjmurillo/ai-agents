# Security Review: ADR-042 Python Migration

## Verdict: CONCERNS

**Risk Score**: 5.5/10 (Medium)

The migration improves static analysis posture (CodeQL support) but introduces supply chain and complexity risks that require mitigation controls before proceeding.

---

## Security Posture Assessment

### Improvements

| Factor | Current (PowerShell) | Future (Python) | Delta |
|--------|---------------------|-----------------|-------|
| **Static Analysis (SAST)** | PSScriptAnalyzer only | CodeQL + PSScriptAnalyzer | +2 points |
| **CVE Database Coverage** | Limited (NVD gaps for PS) | Full (PyPI/NVD integration) | +1 point |
| **Security Linting** | Limited | Bandit, safety, pip-audit | +2 points |
| **Dependency Vulnerability Scanning** | None (no package manager) | UV/pip-audit, Dependabot | +2 points |

**CodeQL Impact**: The ADR correctly identifies that CodeQL does not support PowerShell. Migration to Python enables security-extended scanning for all script code.

### Regressions

| Factor | Current (PowerShell) | Future (Python) | Delta |
|--------|---------------------|-----------------|-------|
| **Supply Chain Attack Surface** | Zero (no external deps) | PyPI ecosystem | -3 points |
| **Dual Runtime Complexity** | Single (PowerShell Core) | Dual (PS + Python) during migration | -1 point |
| **Secrets Handling Patterns** | Established (Test-SafeFilePath) | Must reimplement | -1 point |

**Net Assessment**: +2 points improvement in security posture, contingent on supply chain controls.

---

## New Attack Surfaces

### Attack Surface 1: PyPI Supply Chain (Risk: High)

**CWE Reference**: CWE-1357 (Reliance on Insufficiently Trustworthy Component)

**Description**: Python migration introduces dependency on PyPI ecosystem. Current state has zero external script dependencies. Future state inherits all PyPI risks.

**Threat Vectors**:

- Dependency confusion attacks (internal package names colliding with PyPI)
- Typosquatting on common packages
- Malicious package updates
- Compromised maintainer accounts

**Current Mitigations Found**: None. `requirements.txt` exists with `anthropic>=0.39.0` but no lock file, no hash pinning.

**Risk Score**: 7/10 (High)

### Attack Surface 2: UV Package Manager (Risk: Medium)

**CWE Reference**: CWE-494 (Download of Code Without Integrity Check)

**Description**: UV is a new package manager (Astral, released 2024). Newer tooling has less security research.

**Mitigations Found**:

- UV is open source (auditable): https://github.com/astral-sh/uv
- Active development with security focus
- Faster than pip (reduces window for MITM)

**Risk Score**: 4/10 (Medium)

### Attack Surface 3: Dual Runtime During Migration (Risk: Low)

**Description**: Hybrid PowerShell/Python state during migration expands attack surface. Two runtimes, two test frameworks, two sets of security patterns.

**Risk Score**: 3/10 (Low, time-bounded)

---

## Supply Chain Controls Required

### Before Migration (BLOCKING)

| Control | CWE | Priority | Effort |
|---------|-----|----------|--------|
| Create `uv.lock` with hash pinning | CWE-1357 | P0 | Low |
| Add `pip` ecosystem to Dependabot | CWE-1357 | P0 | Low |
| Add `pip-audit` to CI pipeline | CWE-1357 | P0 | Medium |
| Document path validation pattern for Python | CWE-22 | P0 | Low |

### During Migration (REQUIRED)

| Control | CWE | Priority | Effort |
|---------|-----|----------|--------|
| Port `Test-SafeFilePath` to Python utility | CWE-22 | P1 | Low |
| Add Bandit security linting | Multiple | P1 | Medium |
| Require type hints (mypy) | CWE-704 | P1 | Medium |

### Post-Migration (RECOMMENDED)

| Control | CWE | Priority | Effort |
|---------|-----|----------|--------|
| SBOM generation | CWE-1357 | P2 | Low |
| Secrets scanning (gitleaks) | CWE-798 | P2 | Low |

---

## Required Dependabot Update

Current `dependabot.yml` tracks GitHub Actions only. Must add:

```yaml
- package-ecosystem: "pip"
  directory: "/"
  schedule:
    interval: "weekly"
```

---

## Recommendation

**Accept ADR-042 with conditions.**

The security benefits of CodeQL Python support outweigh the supply chain risks, provided the following controls are implemented:

### P0 (Before Merge)

1. Create `uv.lock` file with hash-pinned dependencies
2. Add `pip` ecosystem to `dependabot.yml`
3. Document Python security patterns (port from PowerShell)

### P1 (Before Phase 2)

1. Add `pip-audit` to CI workflow
2. Implement Python path validation utility
3. Create Python security checklist for code review

### P2 (Before Phase 3)

1. Add Bandit to CI
2. Generate SBOM for dependency transparency

**Rationale**: The user's motivation ("No CodeQL for PowerShell") is valid. Python migration enables CodeQL security-extended scanning, which catches CWE-78, CWE-79, CWE-89, CWE-22, and CWE-798. The supply chain risks are manageable with standard controls.

---

*Reviewer: security*
*Date: 2026-01-17*
