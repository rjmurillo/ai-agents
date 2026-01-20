# Security Agent Benchmark Suite

> **Purpose**: Validate security agent's ability to REVIEW and INTERPRET security findings.
> **Source**: Issue #756 (Security Agent Detection Gaps Remediation)
> **Language**: Python only (per ADR-042)

## Overview

This benchmark suite tests the security agent's **interpretation capabilities**, not detection.

### Division of Labor

| Component | Responsibility | How |
|-----------|----------------|-----|
| **CodeQL** | Detection | Automated static analysis via GitHub Actions |
| **PSScriptAnalyzer** | Detection (PowerShell) | Automated static analysis |
| **Security Agent** | Interpretation | Reviews findings in project context, recommends mitigations |
| **Benchmarks** | Validation | Tests agent's review quality against known vulnerable code |

### What Benchmarks Test

**[CORRECT]** Security agent's ability to:

- Review CodeQL findings and provide business context
- Assess severity based on deployment context (CLI tool vs API service)
- Recommend specific mitigations with rationale
- Identify false positives that automated tools flag incorrectly

**[INCORRECT]** Benchmarks do NOT test:

- Agent's ability to detect vulnerabilities (that is CodeQL's job)
- Automated scanning capabilities (use CodeQL workflow)
- Detection coverage metrics (measure via GitHub Security tab)

### How It Works

```text
1. CodeQL detects vulnerability (automated)
   |
   v
2. Benchmark presents vulnerable code to agent
   |
   v
3. Agent REVIEWS code (as if CodeQL flagged it)
   |
   v
4. Agent produces interpretation:
   - Business impact assessment
   - Severity calibration for deployment context
   - Specific remediation recommendations
   |
   v
5. Benchmark validates agent's review quality
```

## Structure

```text
.agents/security/benchmarks/
    README.md                           # This file
    conftest.py                         # pytest configuration
    test_cwe22_path_traversal.py        # CWE-22 test cases
    test_cwe77_command_injection.py     # CWE-77 test cases
    vulnerable_samples/                 # Raw vulnerable code for agent review
        cwe22_path_traversal.py         # Path traversal vulnerabilities
        cwe77_command_injection.py      # Command injection vulnerabilities
```

## Running Benchmarks

### Manual Agent Review

Run security agent on benchmark files to verify interpretation quality:

```bash
# Using Task tool (Claude Code)
# Agent reviews vulnerable code as if CodeQL already flagged it
Task(subagent_type='security', prompt='Review .agents/security/benchmarks/vulnerable_samples/')
```

### Automated Testing

Run pytest to verify the benchmark infrastructure:

```bash
cd /path/to/ai-agents
uv run pytest .agents/security/benchmarks/ -v
```

### CodeQL Integration

The security agent workflow now fetches CodeQL alerts before manual review:

```bash
# Pre-commit security check with CodeQL integration
python scripts/security/invoke_precommit_security.py

# Skip CodeQL fetch (offline mode)
python scripts/security/invoke_precommit_security.py --skip-codeql
```

This ensures the agent reviews all automated findings before producing its assessment.

## Test Case Format

Each test case follows this annotation format in Python:

```python
# VULNERABLE: CWE-XX [Brief description]
# EXPECTED: [SEVERITY] - [What agent should detect]
# SOURCE: PR #NNN or "Synthetic"
vulnerable_code_here
```

## Benchmark Categories

### CWE-22: Path Traversal (6 test cases)

| ID | Pattern | Source | Expected |
|----|---------|--------|----------|
| PT-001 | startswith without normalization | PR #752 | CRITICAL |
| PT-002 | os.path.join with absolute path | Synthetic | HIGH |
| PT-003 | Symlink bypass (TOCTOU) | Synthetic | HIGH |
| PT-004 | Null byte injection | Synthetic | CRITICAL |
| PT-005 | False positive (safe pattern) | GitHubCore.psm1 | PASS |
| PT-006 | Path object without validation | Synthetic | HIGH |

### CWE-77: Command Injection (7 test cases)

| ID | Pattern | Source | Expected |
|----|---------|--------|----------|
| CI-001 | shell=True with user input | PR #752 | CRITICAL |
| CI-002 | Dynamic code with user input | Synthetic | CRITICAL |
| CI-003 | Dynamic code with config | Synthetic | HIGH |
| CI-004 | Shell metacharacters in git | Synthetic | CRITICAL |
| CI-005 | False positive (list args) | Safe pattern | PASS |
| CI-006 | False positive (predefined commands) | Safe pattern | PASS |
| CI-007 | Unsafe deserialization | Synthetic | CRITICAL |

## Verification Procedure

1. Fetch CodeQL alerts via `invoke_precommit_security.py` (automated detection)
2. Run security agent on `vulnerable_samples/` directory (interpretation)
3. Collect agent review in `.agents/security/SR-benchmark-*.md`
4. Evaluate interpretation quality:
   - Did agent correctly assess business impact?
   - Did agent provide specific, actionable remediation?
   - Did agent calibrate severity for deployment context?
5. Document interpretation gaps for improvement

## Success Criteria

**Detection** (CodeQL responsibility):

| Metric | Target | Measured By |
|--------|--------|-------------|
| CWE coverage | security-extended suite | GitHub Security tab |
| Automated blocking | Critical findings | CI/CD workflow |

**Interpretation** (Agent responsibility):

| Metric | Target | Current |
|--------|--------|---------|
| Review completeness | 100% findings reviewed | Pending |
| Mitigation specificity | Actionable recommendations | Pending |
| Context calibration | Severity adjusted for deployment | Pending |
| False positive identification | Correct acceptance rationale | Pending |

## Adding New Test Cases

1. Add vulnerable Python code to `vulnerable_samples/` with annotations
2. Add pytest case to appropriate `test_cwe*.py` file
3. Document in this README under appropriate category
4. Update expected detection count

## Python-Only Policy

Per ADR-042 (Python-first), all vulnerable samples are written in Python.
This ensures:

- Consistent testing across the AI/ML ecosystem
- No dual PowerShell/Python maintenance burden
- Alignment with bandit and pip-audit tooling

## References

- [Security Agent Prompt](../../../src/claude/security.md)
- [Severity Criteria](../../governance/SECURITY-SEVERITY-CRITERIA.md)
- [CWE-699 Framework](https://cwe.mitre.org/data/definitions/699.html)
- [Issue #755 Security Agent Failure](https://github.com/rjmurillo/ai-agents/issues/755)
- [Issue #756 Detection Gaps Remediation](https://github.com/rjmurillo/ai-agents/issues/756)
- [ADR-042 Python-First](../../architecture/ADR-042-python-first.md)
