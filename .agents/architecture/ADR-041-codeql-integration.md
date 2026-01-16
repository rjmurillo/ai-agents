# ADR-041: CodeQL Integration Multi-Tier Strategy

**Status**: Accepted
**Date**: 2026-01-16
**Deciders**: Repository Owner, Security Agent, Implementer Agent
**Context**: Implementing comprehensive static security analysis

---

## Context and Problem Statement

The repository requires static security analysis to detect vulnerabilities before they reach production. Key requirements include:

1. **Automated enforcement**: Security scanning must be part of CI/CD pipeline
2. **Developer feedback**: Enable local scanning during development
3. **Just-in-time analysis**: Provide immediate feedback during code editing
4. **Shared configuration**: Consistent query packs across all tiers
5. **Performance**: Scans must complete within acceptable timeframes
6. **Graceful degradation**: System should work even when CLI unavailable

**Key Question**: How should CodeQL be integrated to provide comprehensive security analysis without disrupting developer workflow?

---

## Decision Drivers

1. **Security Coverage**: Need comprehensive vulnerability detection across codebase
2. **Developer Experience**: Local scanning must be fast and non-intrusive
3. **CI/CD Integration**: Must block PRs with critical security findings
4. **Performance**: Scans must complete within workflow timeout budgets
5. **Consistency**: Same query packs used across all environments
6. **Tooling Familiarity**: Integrate with existing tools (VSCode, Claude Code)
7. **Graceful Degradation**: Optional CLI for local development
8. **Cost Efficiency**: Leverage GitHub Actions minutes efficiently

---

## Considered Options

### Option 1: CI-Only Integration

**Run CodeQL only in GitHub Actions workflow**

**Pros**:
- ✅ Simple implementation (single workflow)
- ✅ Guaranteed execution on all PRs
- ✅ No local setup required
- ✅ Centralized SARIF upload

**Cons**:
- ❌ Late feedback (only after PR creation)
- ❌ No local development scanning
- ❌ Developers can't iterate quickly
- ❌ Wastes review time on preventable issues

**Why Not Chosen**: Feedback too late in development cycle; forces developers to wait for CI

### Option 2: Local-Only Integration

**Provide only local scanning tools (VSCode tasks, scripts)**

**Pros**:
- ✅ Fast feedback during development
- ✅ No CI/CD time consumption
- ✅ Developer control over scan frequency

**Cons**:
- ❌ No enforcement mechanism
- ❌ Relies on developer discipline
- ❌ No automatic SARIF upload
- ❌ Inconsistent adoption across team
- ❌ Vulnerabilities can reach production

**Why Not Chosen**: No enforcement; optional scanning allows vulnerabilities to slip through

### Option 3: IDE Extension Only

**Use only CodeQL VSCode extension**

**Pros**:
- ✅ Integrated into editor
- ✅ Real-time feedback
- ✅ Official GitHub tooling

**Cons**:
- ❌ VSCode-only (not cross-platform for all editors)
- ❌ Requires manual extension installation
- ❌ No CI/CD integration
- ❌ No Claude Code integration
- ❌ Limited to interactive editing

**Why Not Chosen**: Locks into VSCode; no enforcement; incompatible with automation

### Option 4: Multi-Tier with Shared Configuration (CHOSEN)

**Implement three-tier strategy with shared configuration**

**Pros**:
- ✅ Comprehensive coverage across all workflow stages
- ✅ Enforcement via CI/CD (Tier 1)
- ✅ Fast local development feedback (Tier 2)
- ✅ Automatic just-in-time analysis (Tier 3)
- ✅ Shared configuration ensures consistency
- ✅ Database caching improves performance
- ✅ Graceful degradation when CLI unavailable
- ✅ Integrates with existing tools (VSCode, Claude Code)

**Cons**:
- ❌ Higher implementation complexity
- ❌ Requires CodeQL CLI installation for local use
- ❌ Additional disk space for cached databases
- ❌ More components to maintain

**Why Chosen**: Provides comprehensive security coverage while maintaining developer experience; enforcement + feedback + automation

---

## Decision Outcome

**Chosen option: Option 4 - Multi-Tier with Shared Configuration**

### Rationale

The multi-tier strategy addresses all key requirements:

1. **Tier 1 (CI/CD)**: Enforcement mechanism preventing vulnerabilities from merging
2. **Tier 2 (Local)**: Fast feedback enabling developers to fix issues before PR
3. **Tier 3 (Automatic)**: Just-in-time analysis during active development
4. **Shared Configuration**: Single source of truth for query packs and settings

### Architecture

```text
Tier 1 (CI/CD)
├── Trigger: All PRs, main branch pushes
├── Execution: GitHub Actions workflow
├── Configuration: .github/codeql/codeql-config.yml
├── Behavior: Blocking (critical findings prevent merge)
└── Output: SARIF upload to Security tab

Tier 2 (Local Development)
├── Trigger: Developer-initiated
├── Execution: VSCode tasks, Claude Code skill
├── Configuration: .github/codeql/codeql-config.yml (shared)
├── Behavior: On-demand, with database caching
└── Output: Local SARIF results

Tier 3 (Automatic Scanning)
├── Trigger: PostToolUse hook (Edit/Write/NotebookEdit)
├── Execution: Background process
├── Configuration: .github/codeql/codeql-config-quick.yml
├── Behavior: Non-blocking, graceful degradation
└── Output: Console warnings
```

### Implementation Components

**Installation**:
- `.codeql/scripts/Install-CodeQL.ps1` - CLI installation
- `.codeql/scripts/Install-CodeQLIntegration.ps1` - One-command setup

**Scanning**:
- `.codeql/scripts/Invoke-CodeQLScan.ps1` - Main scanning script
- `.codeql/scripts/Test-CodeQLConfig.ps1` - Configuration validation
- `.codeql/scripts/Get-CodeQLDiagnostics.ps1` - Health checks

**Configuration**:
- `.github/codeql/codeql-config.yml` - Shared configuration (full scan)
- `.github/codeql/codeql-config-quick.yml` - Quick scan (targeted queries)

**Integration**:
- `.github/workflows/codeql-analysis.yml` - CI/CD workflow
- `.vscode/tasks.json` - VSCode tasks
- `.claude/skills/codeql-scan/` - Claude Code skill
- `.claude/hooks/PostToolUse/Invoke-CodeQLQuickScan.ps1` - Automatic hook

**Testing**:
- `tests/Install-CodeQL.Tests.ps1` - CLI installation tests
- `tests/Invoke-CodeQLScan.Tests.ps1` - Scanning tests
- `tests/CodeQL-Integration.Tests.ps1` - End-to-end integration tests

### Trade-offs

**Complexity vs Coverage**:
- **Trade-off**: Three tiers add implementation complexity
- **Justification**: Comprehensive coverage worth the complexity
- **Mitigation**: Clear documentation, one-command setup script

**Performance vs Thoroughness**:
- **Trade-off**: Full scans take 30-60 seconds
- **Justification**: Database caching reduces subsequent scans to 10-20 seconds
- **Mitigation**: Quick configuration for PostToolUse hook (5-15 seconds)

**Optional vs Required**:
- **Trade-off**: Local CLI installation is optional
- **Justification**: Graceful degradation maintains usability
- **Mitigation**: CI/CD enforcement catches what local scanning misses

---

## Consequences

### Positive

1. **Security Assurance**: All code changes scanned before merge
2. **Fast Feedback**: Developers find and fix issues during development
3. **Consistent Standards**: Shared configuration ensures uniform query packs
4. **Performance Optimization**: Database caching reduces scan times by 3-5x
5. **Graceful Degradation**: System functional even without local CLI
6. **Tool Integration**: Works with VSCode and Claude Code workflows
7. **Visibility**: SARIF upload provides security dashboard in GitHub
8. **Maintainability**: Single configuration file reduces update burden

### Negative

1. **Implementation Complexity**: Three tiers require more components
   - **Mitigation**: Comprehensive documentation and one-command installer
2. **CLI Installation Required**: Local scanning needs CodeQL CLI
   - **Mitigation**: Automated installation script, graceful degradation
3. **Disk Space**: Cached databases consume 100-300MB per language
   - **Mitigation**: Gitignore database directories, clear cache when needed
4. **CI/CD Time**: Adds 30-60 seconds to pull request checks
   - **Mitigation**: Parallel language scans, database caching for subsequent runs
5. **Maintenance Burden**: More components to update and test
   - **Mitigation**: Shared configuration, comprehensive test suite

### Neutral

1. **Learning Curve**: Developers must understand CodeQL workflow
   - **Mitigation**: User documentation, FAQ section, troubleshooting guide
2. **False Positives**: May require suppression comments
   - **Mitigation**: Documentation on suppression patterns, clear error messages
3. **Language Coverage**: Currently PowerShell, Python, and GitHub Actions
   - **Mitigation**: Architecture supports adding languages incrementally

---

## Implementation Notes

### Database Caching Strategy

**Cache Location**: `.codeql/db/{language}/`

**Invalidation Triggers**:
- Git HEAD changes (new commits)
- Configuration file updates
- Source file modifications in scanned paths
- Manual force rebuild (`-Force` flag)

**Benefits**:
- First scan: ~60 seconds
- Cached scan: ~15 seconds (3-4x speedup)
- Enables frequent local scanning

### Query Pack Selection

**Full Configuration** (`codeql-config.yml`):
- Query pack: `security-extended`
- Coverage: All security vulnerabilities + common coding errors
- Use cases: CI/CD, comprehensive local scans

**Quick Configuration** (`codeql-config-quick.yml`):
- Query pack: `security-extended` with CWE tags
- Queries: CWE-078, CWE-079, CWE-089, CWE-022, CWE-798
- Use cases: PostToolUse hook, rapid feedback

### Exit Code Standards (ADR-035)

All scripts follow standardized exit codes:
- `0`: Success (scan completed)
- `1`: Failure (scan failed or findings above threshold)
- `3`: Validation error (invalid configuration)

### Performance Budgets

- **Tier 1 (CI/CD)**: 300 seconds timeout
- **Tier 2 (Local)**: 60 seconds timeout (default)
- **Tier 3 (Automatic)**: 30 seconds timeout

### Security Considerations

1. **Query Pack Trust**: Pin versions, prefer official packs
2. **SARIF Output**: Gitignored, uploaded only to private Security tab
3. **Database Storage**: Gitignored, restrict permissions
4. **Workflow Permissions**: Least privilege (contents:read, security-events:write)

### Operational Status

| Tier | Status | Investment Policy |
|------|--------|------------------|
| Tier 1 (CI/CD) | **Active Development** | Continue enhancements, maintain quality |
| Tier 2 (Local) | **Maintenance-Only** | Bug fixes only, no new features |
| Tier 3 (Automatic) | **Maintenance-Only** | Bug fixes only, no new features |

**Rationale**: CI/CD enforcement provides core security value. Local/automatic tiers are developer convenience features subject to usage validation per post-deployment review (see below).

**Re-evaluation**: If 6-month review shows positive ROI for Tiers 2-3, upgrade to "Active Development" status. If negative ROI or unused, create amendment ADR to deprecate and simplify to CI-only.

### Post-Deployment Validation

**Evaluation Criteria** (6-month review: 2026-07-16):

1. **Tier 2 Adoption**: Developer usage of local scanning (check git logs for `codeql` mentions)
2. **Tier 3 Effectiveness**: Vulnerabilities caught by PostToolUse hook vs CI-only
3. **Maintenance Cost**: Hours spent on CodeQL-related fixes and updates
4. **False Positive Rate**: Warning dismissal patterns in session logs

**Success Metrics**:
- Tier 2: >3 developers use local scanning monthly
- Tier 3: Catches ≥1 vulnerability per quarter that CI would have caught
- Maintenance: <10% of development time

**Failure Criteria**: If metrics show Tiers 2-3 unused or negative ROI, create amendment ADR to simplify to CI-only.

### Architectural Trade-offs Accepted

**Workflow Complexity**: The `.github/workflows/codeql-analysis.yml` exceeds ADR-006's 100-line guideline (292 lines) due to three-tier orchestration requirements. This complexity is accepted because:
- Logic is properly delegated to PowerShell scripts
- YAML provides only orchestration (no business logic)
- Reduction would require sacrificing tier isolation

**Platform Lock-in**: This architecture depends on GitHub-specific infrastructure:
- GitHub Actions for CI/CD (Tier 1)
- GitHub Security tab for SARIF upload
- GitHub Releases for CLI distribution

**Mitigation**: Tier 1 is portable (CodeQL CLI works on any CI/CD platform). Tiers 2-3 are convenience layers.

---

## Related Decisions

- [ADR-005: PowerShell-Only Scripting](./ADR-005-powershell-only-scripting.md) - All scripts use PowerShell
- [ADR-006: Thin Workflows, Testable Modules](./ADR-006-thin-workflows-testable-modules.md) - Logic in PowerShell modules
- [ADR-035: Exit Code Standardization](./ADR-035-exit-code-standardization.md) - Standard exit codes for all scripts
- Memory: `security-infrastructure-review` - Security infrastructure patterns
- Memory: `ci-infrastructure-quality-gates` - Quality gate implementation

---

## References

### CodeQL Documentation
- [CodeQL Overview](https://codeql.github.com/docs/codeql-overview/)
- [Supported Languages](https://codeql.github.com/docs/codeql-overview/supported-languages-and-frameworks/)
- [Query Packs](https://codeql.github.com/docs/codeql-cli/about-codeql-packs/)

### GitHub Actions
- [CodeQL Action](https://github.com/github/codeql-action)
- [SARIF Upload](https://docs.github.com/en/code-security/code-scanning/integrating-with-code-scanning/sarif-support-for-code-scanning)
- [Security Best Practices](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions)

### Standards
- [SARIF Specification v2.1.0](https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html)
- [CWE Top 25 Most Dangerous Software Weaknesses](https://cwe.mitre.org/top25/archive/2023/2023_top25_list.html)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)

### Repository Documentation
- [User Guide](../../docs/codeql-integration.md)
- [Architecture Details](../../docs/codeql-architecture.md)
- [Installation Scripts](../../.codeql/scripts/)
- [Test Suite](../../tests/)

---

## Validation

Before marking this ADR as complete:
- [x] All three tiers implemented and tested
- [x] Shared configuration created and validated
- [x] Database caching implemented with invalidation
- [x] CI/CD workflow tested on sample PRs
- [x] VSCode integration configured
- [x] Claude Code skill functional
- [x] PostToolUse hook tested with graceful degradation
- [x] Comprehensive test suite passing
- [x] Documentation complete (user guide, architecture, ADR)
- [x] Pester tests for all PowerShell scripts
- [x] Exit codes follow ADR-035 standards
- [x] Gitignore configured for databases and results
- [x] Performance budgets met across all tiers

---

**Supersedes**: None (new decision)
**Amended by**: None
