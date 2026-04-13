# Security Review Protocol

> **Purpose**: Define the security review workflow including CodeQL integration and immediate RCA trigger for false negatives.
> **Source**: Issue #756 (Security Agent Detection Gaps Remediation)

## Overview

The security review process has two phases:

1. **Pre-implementation**: Security agent analyzes proposed changes for vulnerabilities
2. **Post-implementation**: Security agent verifies implemented controls, external reviewers validate

When external reviewers (Gemini Code Assist, human reviewers) identify vulnerabilities the security agent missed, this triggers an immediate Root Cause Analysis (RCA) workflow.

## Division of Labor

| Component | Responsibility | Details |
|-----------|----------------|---------|
| **CodeQL** | Automated detection | CWE patterns in Python, GitHub Actions |
| **PSScriptAnalyzer** | Automated detection | PowerShell security rules |
| **Security Agent** | Interpretation and context | Reviews findings, assesses business impact |
| **Benchmarks** | Agent validation | Tests interpretation quality |

**Key Principle**: CodeQL detects, agent interprets. Do not duplicate detection logic in agent.

## Security Agent Workflow

### Step 0: Check CodeQL Alerts FIRST (Required)

**BEFORE manual code review**, security agent MUST fetch CodeQL alerts:

```bash
# Automated via pre-commit hook
python scripts/security/invoke_precommit_security.py

# Or via GitHub API directly
gh api repos/{owner}/{repo}/code-scanning/alerts \
  --jq '.[] | select(.state=="open")'
```

**Why**: Prevents missing vulnerabilities that automated tools already detected. The agent's value is interpretation, not detection.

### Step 1: Review CodeQL Findings in Context

For each CodeQL alert, the agent assesses:

1. **Business impact**: What data or systems are at risk?
2. **Deployment context**: CLI tool (local risk) vs API service (network risk)
3. **Existing mitigations**: Are there compensating controls?
4. **Severity calibration**: Adjust based on actual exposure

### Step 2: Manual Code Review

After reviewing automated findings, agent performs additional review for:

1. **Architecture-level vulnerabilities**: Trust boundaries, privilege escalation
2. **Business logic flaws**: Context CodeQL cannot understand
3. **PowerShell code**: CodeQL does not support PowerShell
4. **Configuration issues**: Environment variables, deployment settings

### Step 3: Synthesize Report

Security report MUST include:

1. **CodeQL Findings** section with agent interpretation
2. **Manual Findings** section for non-automated discoveries
3. **Validation Status** showing both CodeQL and manual review status

## Immediate Trigger Workflow

```text
External reviewer identifies vulnerability NOT in agent report
    |
    v
IMMEDIATE RCA Trigger (not monthly batch)
    |
    +---> Run invoke_security_retrospective.py
    |         |
    |         +---> Extract false negative details
    |         +---> Store in Forgetful (semantic memory)
    |         +---> Store in Serena (project memory)
    |         +---> Update security.md prompt
    |         +---> Add benchmark test case
    |
    v
PR Merge BLOCKED until:
    1. security.md updated with new detection pattern
    2. Benchmark test case added
    3. Re-review confirms agent now detects vulnerability
```

## False Negative Response Time

| Severity | Response SLA | Merge Status |
|----------|-------------|--------------|
| CRITICAL | Immediate (same session) | BLOCKED |
| HIGH | Within 24 hours | BLOCKED |
| MEDIUM | Within 7 days | Track in issue |
| LOW | Within 30 days | Document only |

## Running the Retrospective

When an external reviewer identifies a missed vulnerability:

```bash
# Standard invocation
python scripts/security/invoke_security_retrospective.py \
    --pr-number 752 \
    --source Gemini

# Dry run (preview changes)
python scripts/security/invoke_security_retrospective.py \
    --pr-number 752 \
    --source Manual \
    --dry-run
```

## Worked Examples

### Example 1: CWE-22 Path Traversal (PR #752)

**Context**: Export-ClaudeMemMemories.ps1 contained a path traversal vulnerability at line 115.

**What Security Agent Found**: Nothing related to path traversal.

**What External Reviewer Found**:

> "CRITICAL: CWE-22 Path Traversal. The `$OutputFile` parameter is validated using `StartsWith()` without path normalization. Attack: `$OutputFile = "..\..\..\etc\passwd"` passes the check but escapes the intended directory."

**Why It Was Missed**:

1. security.md did not have explicit `StartsWith()` detection pattern
2. PowerShell checklist lacked path normalization requirement
3. Agent relied on general CWE-22 knowledge without PowerShell-specific guidance

**Corrective Actions**:

1. [x] Added "Path Traversal Prevention" section to security.md
2. [x] Added `GetFullPath()` normalization pattern to checklist
3. [x] Created benchmark test case PT-001 in cwe22-path-traversal.ps1
4. [x] Stored false negative in Forgetful (importance=10)
5. [x] Created Serena memory for project-specific context

**Detection Pattern Added**:

```markdown
#### Path Traversal Prevention (CWE-22)

- [ ] Use `[System.IO.Path]::GetFullPath()` to normalize paths before validation
- [ ] Never trust `StartsWith()` for path containment without normalization
```

**Verification**: Re-run security agent on Export-ClaudeMemMemories.ps1. Agent now flags line 115.

### Example 2: CWE-77 Command Injection (PR #752)

**Context**: Same PR had unquoted variables in npx command at line 42.

**What Security Agent Found**: Nothing related to command injection.

**What External Reviewer Found**:

> "CRITICAL: CWE-77 Command Injection. Unquoted variables `$Query` and `$OutputFile` in external command allow shell metacharacters (;|&><) to inject additional commands."

**Why It Was Missed**:

1. security.md CWE list only had CWE-78 (OS command injection), not CWE-77 (command injection)
2. No PowerShell-specific pattern for quoting variables in external commands
3. Agent did not flag npx/node/python commands differently from PowerShell cmdlets

**Corrective Actions**:

1. [x] Added CWE-77 to security.md CWE list
2. [x] Added "Command Injection Prevention" section with quoting pattern
3. [x] Created benchmark test case CI-001 in cwe77-command-injection.ps1
4. [x] Added external command list (npx, node, python, git, gh) to checklist

**Detection Pattern Added**:

```markdown
#### Command Injection Prevention (CWE-77, CWE-78)

- [ ] All variables in external commands are quoted (`"$Variable"` not `$Variable`)
- [ ] Check for unquoted variables in: `npx`, `node`, `python`, `git`, `gh`, `pwsh`, `bash`
```

**Verification**: Re-run security agent. Agent now flags unquoted variables in external commands.

### Example 3: False Positive Handling

**Context**: Security agent flags `Test-SafeFilePath` function as CWE-22 vulnerable.

**What Agent Found**:

> "HIGH: CWE-22 potential. Function uses `StartsWith()` for path validation."

**Why This Is a False Positive**:

The function uses `GetFullPath()` BEFORE `StartsWith()`, which is the correct pattern:

```powershell
function Test-SafeFilePath {
    param([string]$Path, [string]$AllowedRoot)
    $NormalizedPath = [System.IO.Path]::GetFullPath($Path)  # Normalizes first
    $NormalizedRoot = [System.IO.Path]::GetFullPath($AllowedRoot)
    return $NormalizedPath.StartsWith($NormalizedRoot, [StringComparison]::OrdinalIgnoreCase)
}
```

**How to Document Acceptance**:

1. Review the code to confirm GetFullPath is called before StartsWith
2. Add inline comment: `# SECURITY: Safe pattern - GetFullPath normalizes before StartsWith`
3. Add to benchmark suite as false positive test case (PT-005)
4. If agent repeatedly flags, add to security.md "Safe Patterns" section

**Safe Pattern Documentation**:

```markdown
### Safe Patterns (Do Not Flag)

- `Test-SafeFilePath` from GitHubCore.psm1 (uses GetFullPath before StartsWith)
- GraphQL variables for parameter passing (not string interpolation)
- `ValidateSet` attributes on parameters (restricts input to known values)
```

## Memory Integration

False negatives are stored in two memory systems:

### Forgetful (Semantic Memory)

Enables cross-project pattern search:

```python
# Query for all false negatives
mcp__forgetful__execute_forgetful_tool(
    "query_memory",
    {
        "query": "security false negative CWE-22",
        "query_context": "security retrospective"
    }
)
```

### Serena (Project Memory)

Enables project-specific RCA retrieval:

```text
.serena/memories/security-false-negative-cwe-22-pr752.md
```

## Escalation Path

| Condition | Action |
|-----------|--------|
| False negative in CRITICAL file pattern | Immediate escalation to security team |
| Same CWE missed twice | Add to mandatory detection list |
| Benchmark detection rate < 90% | Security agent prompt revision required |
| External reviewer finds > 3 misses | Full security.md audit required |

## References

- [Security Severity Criteria](SECURITY-SEVERITY-CRITERIA.md)
- [Security Agent Prompt](../../src/claude/security.md)
- [Benchmark Suite](../.agents/security/benchmarks/README.md)
- [PR #752 RCA](../analysis/security-agent-failure-rca.md)
- [Issue #755](https://github.com/rjmurillo/ai-agents/issues/755)
- [Issue #756](https://github.com/rjmurillo/ai-agents/issues/756)
