# CodeQL Security Integration Pattern

**Importance**: HIGH  
**Date**: 2026-01-19  
**Session**: 14  
**Issue**: #756

## The Pattern

**Don't build custom detection when CodeQL already exists.**

## Division of Labor

| Task | Owner | Rationale |
|------|-------|-----------|
| Detect CWE-22/CWE-77 in Python | CodeQL | Automated > manual, 408+ queries |
| Interpret findings in context | Security Agent | Requires architecture knowledge |
| PowerShell security review | Security Agent + PSScriptAnalyzer | CodeQL doesn't support PowerShell |
| Blocking gate on critical issues | CodeQL | Automated enforcement in CI |
| Threat modeling | Security Agent | Requires business context |

## Implementation

### Security Agent Workflow

1. **Fetch CodeQL alerts** (Step 0):
   ```bash
   gh api /repos/{owner}/{repo}/code-scanning/alerts \
     --jq '.[] | select(.state=="open" and .ref=="refs/heads/{branch}")'
   ```

2. **Interpret in context**: Agent reviews with architecture knowledge
3. **Generate report**: Include CodeQL findings + contextual analysis

### What CodeQL Provides

- **Python**: CWE-22 (path traversal), CWE-78 (command injection), 160+ CWEs
- **SARIF output**: Structured machine-readable findings
- **GitHub integration**: Security tab, PR checks, blocking gates
- **Default suite**: 408 queries
- **Extended suite**: 539 queries

### What Security Agent Adds

- Contextual interpretation (is this actually exploitable?)
- Severity calibration based on deployment context
- Remediation guidance with rationale
- Multi-language support (Python + PowerShell)
- Threat modeling

## Gap Analysis (Issue #756 RCA)

**Why #755 vulnerabilities were missed**:
- Security agent didn't check CodeQL results first
- CodeQL detected CWE-22/CWE-77 but agent didn't fetch SARIF
- Agent attempted manual detection, failed

**Fix Applied**:
- `invoke_precommit_security.py` now fetches CodeQL alerts as Step 0
- Security report includes "CodeQL Findings" section
- Benchmarks test agent REVIEW capability, not detection

## Related

- `.agents/analysis/756-codeql-vs-custom-detection-analysis.md`
- `scripts/security/invoke_precommit_security.py`
- `.agents/security/benchmarks/README.md` (clarifies benchmark purpose)
