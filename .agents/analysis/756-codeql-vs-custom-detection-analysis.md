# Analysis: CodeQL vs Custom Security Detection

## 1. Objective and Scope

**Objective**: Determine whether custom CWE-22 and CWE-77 detection mechanisms duplicate CodeQL capabilities and recommend optimal division of labor.

**Scope**: This analysis covers CodeQL workflows in this codebase, CodeQL's native Python CWE detection, custom benchmark infrastructure, and security agent responsibilities.

## 2. Context

### User Concern

Building custom CWE-22 (path traversal) and CWE-77 (command injection) detectors is redundant when CodeQL exists and already scans Python code.

### Current State

**CodeQL Workflow** (`.github/workflows/codeql-analysis.yml`):
- Scans Python and GitHub Actions languages
- Uses `security-extended` query packs
- Runs on PRs, pushes to main, and weekly schedule
- Filters findings to medium+ severity
- Uploads SARIF results to GitHub Security tab
- Blocks PRs on critical findings (severity >= 9.0)

**Custom Benchmark Infrastructure** (`.agents/security/benchmarks/`):
- Python test cases for CWE-22 (5 patterns) and CWE-77 (5 patterns)
- Designed to test "security agent" detection capabilities
- No actual detection code exists, only test fixtures

**Security Agent** (`src/vs-code-agents/security.agent.md`):
- Human-like security reviewer (LLM-based)
- Performs manual code review with CWE knowledge
- Reviews entire PR context (code, docs, ADRs, architecture)
- Produces natural language security reports

## 3. Approach

**Methodology**:
1. Inventory CodeQL workflows and configuration
2. Research CodeQL Python query coverage for CWE-22/CWE-77
3. Analyze custom benchmark infrastructure to identify actual detection code
4. Compare CodeQL capabilities vs security agent responsibilities
5. Identify gaps requiring custom detection

**Tools Used**:
- Read CodeQL workflow files
- Read CodeQL configuration (`.github/codeql/codeql-config.yml`)
- Read security benchmarks and conftest.py
- WebSearch for CodeQL Python query capabilities
- Read security agent failure RCA

**Limitations**: Cannot execute CodeQL scans during analysis phase.

## 4. Data and Analysis

### Evidence Gathered

| Finding | Source | Confidence |
|---------|--------|------------|
| CodeQL scans Python with security-extended suite | `.github/workflows/codeql-analysis.yml:12` | High |
| CodeQL has py/path-injection query for CWE-22 | [CodeQL docs](https://codeql.github.com/codeql-query-help/python/py-path-injection/) | High |
| CodeQL has CWE-078/CommandInjection.ql for Python | [GitHub codeql repo](https://github.com/github/codeql/blob/main/python/ql/src/Security/CWE-078/CommandInjection.ql) | High |
| No custom detection code exists in benchmarks | `.agents/security/benchmarks/conftest.py:228-257` | High |
| Security agent missed CWE-22/CWE-77 in PR #752 | `.agents/analysis/security-agent-failure-rca.md` | High |
| Benchmarks only contain test fixtures and pytest cases | `.agents/security/benchmarks/test_cwe22_path_traversal.py` | High |

### Facts (Verified)

1. **CodeQL Python Coverage Exists**: CodeQL includes queries for both CWE-22 (path traversal) and CWE-78 (command injection, closely related to CWE-77).

2. **CodeQL Runs Automatically**: Workflow executes on all PRs targeting main branch, with results uploaded to GitHub Security tab.

3. **No Custom Detection Implementation**: The benchmark suite at `.agents/security/benchmarks/` contains only test fixtures and assertions. The `verify_detection()` function (conftest.py:228-257) accepts `agent_findings` as input but does not perform detection itself.

4. **Security Agent is LLM-Based Reviewer**: The security agent is not an automated scanner but a human-like reviewer powered by Claude Opus 4.5. It performs manual code analysis with CWE awareness.

5. **Benchmark Tests Expect Agent Findings**: Test files call `verify_detection(pattern, agent_findings)` expecting security agent to produce findings in specific format, not automated detection.

6. **CodeQL Blocks Critical Findings**: Workflow includes blocking gate at line 286 that fails PR if critical findings detected (security-severity >= 9.0).

### CodeQL Python Query Coverage

Per [CodeQL documentation](https://codeql.github.com/codeql-query-help/python-cwe/):

**CWE-22 Path Traversal**:
- Query: `py/path-injection`
- Description: Detects accessing files using paths constructed from user-controlled data
- Category: Security-extended suite

**CWE-78 Command Injection**:
- Query: `py/command-injection` (CWE-078/CommandInjection.ql)
- Description: Detects constructing OS commands from user input
- Category: Security-extended suite
- Note: CWE-78 (OS Command Injection) is a specific instance of CWE-77 (Command Injection)

**Additional Related Queries**:
- `py/code-injection`: Detects eval/exec with user input
- `py/shell-command-constructed-from-input`: Shell command construction
- `py/unsafe-deserialization`: Pickle deserialization

### Hypothesis Testing

**Hypothesis**: Custom detection is redundant because CodeQL covers CWE-22 and CWE-77.

**Evidence**:
- **Supporting**: CodeQL has native queries for both CWEs ✓
- **Supporting**: CodeQL runs automatically on all PRs ✓
- **Supporting**: No custom detection code actually exists ✓
- **Contradicting**: Benchmarks suggest expectation of agent-based detection ⚠

**Conclusion**: Hypothesis is PARTIALLY CORRECT. CodeQL provides automated detection, but benchmarks test manual review capabilities.

## 5. Results

### What CodeQL Provides (Automated Static Analysis)

**Strengths**:
1. **Comprehensive Query Library**: 408 security queries in default suite, 539 in extended suite
2. **Automated Execution**: Runs on every PR without manual intervention
3. **SARIF Integration**: Results viewable in GitHub Security tab
4. **Blocking Gates**: Fails PR on critical findings
5. **Low False Positive Rate**: Queries curated by security researchers

**Limitations**:
1. **Language Coverage**: Python and GitHub Actions only (no PowerShell)
2. **Generic Patterns**: May miss domain-specific vulnerabilities
3. **No Context Awareness**: Cannot reason about business logic or architecture
4. **Binary Output**: Flags code as vulnerable or safe, no nuanced analysis

### What Security Agent Provides (Manual Review)

**Strengths**:
1. **Contextual Reasoning**: Reviews code in context of ADRs, architecture, threat model
2. **Business Logic Analysis**: Understands domain-specific security requirements
3. **Multi-Language**: Can review PowerShell, Python, YAML, any language
4. **Remediation Guidance**: Provides specific fix recommendations with rationale
5. **Severity Calibration**: Adjusts severity based on deployment context

**Limitations**:
1. **Inconsistent**: LLM-based, not deterministic
2. **Incomplete Coverage**: Missed CWE-22/CWE-77 in PR #752 despite CodeQL coverage
3. **Manual Trigger**: Requires explicit invocation
4. **No Regression Prevention**: Does not run on every commit

### Gap Analysis

| Capability | CodeQL | Security Agent | Gap |
|------------|--------|----------------|-----|
| Detect CWE-22 in Python | ✓ | ✗ (missed in PR #752) | Security agent needs CodeQL integration |
| Detect CWE-77 in Python | ✓ | ✗ (missed in PR #752) | Security agent needs CodeQL integration |
| Detect PowerShell vulnerabilities | ✗ | ✓ (when prompted) | CodeQL language gap |
| Contextual business logic review | ✗ | ✓ | Security agent strength |
| Automated blocking gate | ✓ | ✗ | CodeQL strength |
| Threat modeling and architecture review | ✗ | ✓ | Security agent strength |

## 6. Discussion

### Root Cause of Redundancy Perception

The benchmark suite structure creates the impression that custom detection is being built:

1. Vulnerable sample files exist (`.agents/security/benchmarks/vulnerable_samples/`)
2. Test cases expect detection (`verify_detection()` function)
3. Severity expectations are defined (`CRITICAL`, `HIGH`, etc.)

However, **no detection implementation exists**. The benchmarks test the security agent's manual review capabilities, not automated scanners.

### Division of Labor

**Optimal Architecture**:

```
┌─────────────────────────────────────────────────────────┐
│                     PR Security Gates                    │
└─────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────┐  ┌──────────────────┐  ┌─────────────┐
│   CodeQL     │  │  Security Agent  │  │  Bandit /   │
│  (Automated) │  │   (Manual LLM)   │  │  pip-audit  │
└──────────────┘  └──────────────────┘  └─────────────┘
        │                   │                   │
        ▼                   ▼                   ▼
  Static Analysis    Contextual Review    Dependency Scan
  • CWE detection    • Architecture       • CVE detection
  • Language: Py     • Business logic     • Known vulns
  • Every commit     • Multi-language     • Every commit
  • Blocking gate    • On-demand          • Advisory
```

**Responsibility Matrix**:

| Detection Type | Primary | Secondary | Rationale |
|----------------|---------|-----------|-----------|
| CWE-22 Python | CodeQL | Security Agent (review CodeQL results) | Automated > manual |
| CWE-77 Python | CodeQL | Security Agent (review CodeQL results) | Automated > manual |
| CWE-22 PowerShell | Security Agent | (none, gap) | CodeQL does not support PowerShell |
| CWE-77 PowerShell | Security Agent | (none, gap) | CodeQL does not support PowerShell |
| Architecture flaws | Security Agent | Independent-Thinker | Requires reasoning |
| Threat modeling | Security Agent | Architect | Requires context |
| Known CVEs | pip-audit / Dependabot | Security Agent (review) | Automated > manual |

### Critical Finding: Security Agent Should Consume CodeQL Results

The security agent failure RCA (`.agents/analysis/security-agent-failure-rca.md`) reveals:

> **CRITICAL-001: Path Traversal (CWE-22)** and **CRITICAL-002: Command Injection (CWE-77)** were missed by security agent in PR #752.

**Root Cause**: Security agent performs manual code review without integrating CodeQL findings.

**Evidence**: Security agent has access to `github/list_code_scanning_alerts` and `github/get_code_scanning_alert` tools (line 11-12 of security.agent.md) but does not use them.

**Impact**: Duplicative effort, missed findings, false confidence.

## 7. Recommendations

### Verdict: DELETE Custom Detection, Integrate CodeQL Results

**Recommendation**: Remove redundant custom detection and integrate CodeQL SARIF output into security agent workflow.

| Priority | Recommendation | Rationale | Effort |
|----------|----------------|-----------|--------|
| P0 | Security agent MUST fetch CodeQL alerts via GitHub API before manual review | Prevent missing automated findings | 1 hour |
| P0 | Document that benchmarks test manual review, not detection | Clarify intent | 30 minutes |
| P1 | Security agent workflow: 1) Fetch CodeQL alerts, 2) Review context, 3) Recommend mitigations | Hybrid approach | 2 hours |
| P1 | Add PowerShell static analysis (PSScriptAnalyzer) to CI | Fill CodeQL language gap | 3 hours |
| P2 | Create skill: `/review-codeql-findings` for interpreting SARIF | Reusable pattern | 4 hours |
| P2 | Benchmark tests should mock CodeQL findings, not expect custom detection | Clarify testing strategy | 2 hours |

### Hybrid Approach: CodeQL Detection + Agent Interpretation

**Recommended Security Agent Workflow**:

1. **Fetch CodeQL Alerts** (automated):
   ```bash
   gh api repos/{owner}/{repo}/code-scanning/alerts \
     --jq '.[] | select(.state=="open")'
   ```

2. **Read SARIF Files** (automated):
   ```powershell
   Get-Content .codeql/results/python.sarif | ConvertFrom-Json
   ```

3. **Manual Review** (agent):
   - Analyze CodeQL findings in context of architecture
   - Assess severity based on deployment context (CLI tool vs API service)
   - Prioritize remediation based on business impact
   - Provide specific fix recommendations with rationale

4. **Report Synthesis** (agent):
   - CodeQL findings (with links to Security tab)
   - Contextual severity adjustments
   - Remediation roadmap
   - Architecture-level recommendations

### What to Keep vs Delete

| Component | Action | Rationale |
|-----------|--------|-----------|
| `.agents/security/benchmarks/` | **KEEP** | Tests security agent manual review capabilities |
| Custom detection code | **DELETE** | Does not exist; no need to build |
| Security agent LLM reviewer | **KEEP** | Provides contextual analysis CodeQL cannot |
| CodeQL workflow | **KEEP** | Automated detection is superior to manual |
| Security agent CodeQL integration | **BUILD** | Critical gap preventing redundancy |

## 8. Conclusion

### Summary

**Core Finding**: No custom detection code exists. The perception of redundancy stems from benchmark test fixtures that expect security agent findings, not automated scanners.

**Actual Redundancy**: Security agent performs manual CWE-22/CWE-77 detection when CodeQL already provides automated detection.

**Resolution**: Security agent should consume CodeQL results and focus on contextual interpretation, not duplicate detection.

### User Impact

**What changes for you**:
1. **Immediate**: No custom detection to delete (none exists)
2. **Short-term**: Security agent workflow updated to fetch CodeQL alerts first
3. **Long-term**: Faster, more accurate security reviews via hybrid approach

**Effort required**:
- Update security agent workflow: 3 hours (P0 + P1)
- Document benchmark intent: 30 minutes (P0)
- Add PSScriptAnalyzer for PowerShell: 3 hours (P1)

**Risk if ignored**:
- Security agent continues missing vulnerabilities CodeQL detects
- Duplicative manual review effort
- False confidence in security posture

### Recommended Division of Labor

**CodeQL (Detection)**:
- Static analysis for Python, GitHub Actions
- CWE-22, CWE-77, CWE-78, CWE-79, CWE-89 detection
- Automated blocking gate on critical findings
- Every commit, every PR

**Security Agent (Interpretation)**:
- Review CodeQL findings in architecture context
- Assess business impact and severity
- Provide remediation roadmap
- Threat modeling and defense-in-depth analysis
- PowerShell security review (CodeQL gap)

**Benchmarks (Validation)**:
- Test security agent's ability to interpret findings
- Provide known-vulnerable samples for agent review
- Validate agent recommendations match best practices

## 9. Appendices

### Sources Consulted

- [CodeQL Python CWE Coverage](https://codeql.github.com/codeql-query-help/python-cwe/)
- [Uncontrolled data used in path expression (py/path-injection)](https://codeql.github.com/codeql-query-help/python/py-path-injection/)
- [CodeQL CommandInjection.ql source](https://github.com/github/codeql/blob/main/python/ql/src/Security/CWE-078/CommandInjection.ql)
- [CodeQL 2.16.3 changelog](https://codeql.github.com/docs/codeql-overview/codeql-changelog/codeql-cli-2.16.3/)
- [CodeQL full CWE coverage](https://codeql.github.com/codeql-query-help/full-cwe/)

### Data Transparency

**Found**:
- CodeQL Python queries for CWE-22 and CWE-78 exist
- CodeQL workflow runs on all PRs
- Security agent has GitHub code scanning API access
- No custom detection implementation in benchmarks
- Security agent missed CWE-22/CWE-77 in PR #752

**Not Found**:
- Custom CWE detection code (does not exist)
- Security agent integration with CodeQL results (gap)
- PowerShell static analysis in CI (gap)

---

**Analyst**: analyst agent
**Date**: 2026-01-19
**Confidence**: HIGH
**Recommendation**: Hybrid approach (CodeQL detection + agent interpretation)
