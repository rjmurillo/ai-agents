# CWE-699 Framework Integration Analysis

**Session**: 307
**Date**: 2026-01-04
**Status**: Research Complete
**Branch**: `feat/security-agent-cwe699-planning`

## Executive Summary

This analysis examines the CWE-699 Software Development weakness view and its specific CWEs (22, 23, 36, 73, 99) related to path traversal vulnerabilities. The research coordinates with the existing security agent detection gaps remediation plan and the PR #752 post-incident findings.

Key findings:

1. CWE-699 organizes weaknesses into 11 primary categories for software development contexts
2. Path traversal weaknesses (CWE-22, 23, 36) form a hierarchical family under CWE-22
3. CWE-73 (External Control of File Name) is the root cause enabling path traversal
4. CWE-99 (Resource Injection) represents the broader class containing file-based attacks
5. OWASP Top 10 maps these to both A01 (Broken Access Control) and A03 (Injection)

The remediation plan's M1 milestone (CWE Coverage Expansion) should prioritize this path traversal family as a unified detection category rather than individual CWEs.

## CWE-699 Software Development View

### Framework Structure

CWE-699 organizes weaknesses into categories based on software development concepts. The view provides abstraction levels from Pillars (most abstract) to Variants (most specific).

Primary categories identified:

| Category | CWE ID | Description |
|----------|--------|-------------|
| API/Function Errors | CWE-1228 | Improper use of APIs and functions |
| Audit/Logging Errors | CWE-1210 | Missing or improper logging |
| Authentication Errors | CWE-1211 | Failure to verify identity |
| Authorization Errors | CWE-1212 | Failure to restrict operations |
| Bad Coding Practices | CWE-1006 | Quality issues enabling vulnerabilities |
| Behavioral Problems | CWE-438 | Unexpected application behavior |
| Business Logic Errors | CWE-840 | Flaws in application logic |

### Path Traversal in CWE-699 Context

Path traversal weaknesses fall under multiple categories:

1. **Input Validation** (primary): Failure to validate pathname input
2. **Authorization Errors**: Accessing files outside permitted scope
3. **Bad Coding Practices**: Using unsafe path operations

## Path Traversal CWE Hierarchy

### CWE-22: Path Traversal (Parent)

**Definition**: Improper limitation of a pathname to a restricted directory.

**Abstraction Level**: Base (sufficient for real-world vulnerability mapping)

**Extended Description**: The product uses external input to construct a pathname intended to identify a file within a restricted directory, but fails to properly neutralize special elements (`..`, `/`, `\`) that can resolve to locations outside that directory.

**Two Primary Variants**:

1. Relative path traversal using `../` sequences (CWE-23)
2. Absolute path traversal using complete paths like `/etc/passwd` (CWE-36)

**Common Consequences**:

| Impact | Scope | Severity |
|--------|-------|----------|
| Execute Unauthorized Code | Integrity, Confidentiality, Availability | CRITICAL |
| Modify Files | Integrity | HIGH |
| Read Files | Confidentiality | HIGH |
| DoS/Crash | Availability | MEDIUM-HIGH |

**OWASP Mapping**: A01:2021 Broken Access Control

### CWE-23: Relative Path Traversal (Child of CWE-22)

**Definition**: Failure to neutralize `..` sequences when constructing file paths from external input.

**Key Distinction**: Specifically targets relative path sequences (`../`) rather than absolute paths.

**Attack Patterns**:

- Standard: `../../../../etc/passwd`
- Directory-based: `../../../filedir`
- Mixed: `dir/../../filename`
- Windows: `..\filedir`
- Obfuscated: `...` (triple dots), `....`, `%2e%2e`
- Zip Slip: Malicious archives with `../` in filenames

**Child Variants**:

| CWE | Pattern |
|-----|---------|
| CWE-24 | `'../filedir'` |
| CWE-25 | `'/../filedir'` |
| CWE-28-35 | Windows-specific and encoded variants |

### CWE-36: Absolute Path Traversal (Child of CWE-22)

**Definition**: Failure to neutralize absolute path sequences when constructing file paths from external input.

**Key Distinction**: Targets complete paths from filesystem root rather than relative sequences.

**Attack Patterns**:

- Unix: `/etc/passwd`, `/absolute/pathname/here`
- Windows: `C:\windows\system32`, `\absolute\pathname\here`
- UNC shares: `\\computername\sharename`

**Critical Insight**: Many path concatenation functions (like Python's `os.path.join()`) discard the base directory when an absolute path is provided as input. This is the root cause of CVE-2022-31503.

**Child Variants**:

| CWE | Pattern |
|-----|---------|
| CWE-37 | Unix-style absolute paths `/absolute/pathname` |
| CWE-38 | Windows-style absolute paths `\absolute\pathname` |
| CWE-39 | Windows drive letters `C:dirname` |
| CWE-40 | UNC shares `\\UNC\share\name\` |

### CWE-73: External Control of File Name or Path

**Definition**: Allowing user input to control or influence paths or file names in filesystem operations.

**Abstraction Level**: Base

**Key Insight**: CWE-73 is the **enabling condition** for path traversal. If an application allows external control of file paths, path traversal becomes possible.

**Two Required Conditions**:

1. Attacker can specify a path used in filesystem operations
2. This specification grants capabilities otherwise unavailable

**Relationship to Path Traversal**:

```text
CWE-73 (External Control) --> enables --> CWE-22 (Path Traversal)
                          --> enables --> CWE-59 (Symlink Following)
                          --> enables --> CWE-434 (Dangerous File Upload)
```

**OWASP Mapping**: A03:2021 Injection (notable CWE in the category)

### CWE-99: Resource Injection

**Definition**: Improper restriction of user input before using it as a resource identifier.

**Abstraction Level**: Class (more abstract than Base)

**Key Insight**: CWE-99 is the **broader class** containing file-based resource injection. It covers not just file paths but also ports, memory locations, and other system resources.

**Relationship to Path Traversal**:

```text
CWE-99 (Resource Injection)
    └── CWE-73 (External Control of File Name/Path)
            └── CWE-22 (Path Traversal)
                    ├── CWE-23 (Relative Path Traversal)
                    └── CWE-36 (Absolute Path Traversal)
```

## OWASP Top 10 2021 Mapping

Path traversal maps to both A01 and A03:

### A01:2021 - Broken Access Control

Path traversal represents unauthorized access to files/directories outside the intended scope. CWE-22 is explicitly listed as a form of Broken Access Control.

### A03:2021 - Injection

CWE-73 is a notable CWE in A03:2021. Injection framing: special characters (`../`) are "injected" to manipulate file paths.

**Why Both Categories?**

- **Access Control Perspective**: Unauthorized file access is an authorization failure
- **Injection Perspective**: Path manipulation uses injected special elements

## PowerShell-Specific Patterns

Based on research and PR #752 findings, these PowerShell patterns are critical for detection:

### Pattern 1: Unvalidated Path Operations

```powershell
# VULNERABLE: Direct use of user input in file operations
$UserPath = $args[0]
Get-Content -Path $UserPath  # CWE-73 + CWE-22

# SAFE: Validate and canonicalize
$BasePath = "/safe/directory"
$UserPath = $args[0]
$FullPath = [System.IO.Path]::GetFullPath((Join-Path $BasePath $UserPath))
if (-not $FullPath.StartsWith($BasePath, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Path traversal attempt detected"
}
Get-Content -Path $FullPath
```

### Pattern 2: StartsWith Without Normalization (PR #752)

```powershell
# VULNERABLE: StartsWith bypassed by ../sequences (CRITICAL-001 from PR #752)
if (-not $OutputFile.StartsWith($MemoriesDir)) {
    Write-Warning "Output file should be in $MemoriesDir"
}
# Attack: $OutputFile = "..\..\..\etc\passwd" passes StartsWith check

# SAFE: Normalize paths before comparison
$NormalizedOutput = [System.IO.Path]::GetFullPath($OutputFile)
$NormalizedDir = [System.IO.Path]::GetFullPath($MemoriesDir)
if (-not $NormalizedOutput.StartsWith($NormalizedDir, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Path traversal attempt blocked"
}
```

### Pattern 3: Join-Path Absolute Path Handling

```powershell
# DANGEROUS: Join-Path with absolute user input
$BasePath = "/safe/directory"
$UserInput = "/etc/passwd"  # Absolute path
$ResultPath = Join-Path $BasePath $UserInput
# Result: /etc/passwd (base path IGNORED)

# SAFE: Validate input is not absolute before joining
if ([System.IO.Path]::IsPathRooted($UserInput)) {
    throw "Absolute paths not allowed"
}
$ResultPath = Join-Path $BasePath $UserInput
```

### Pattern 4: Symbolic Link Following

```powershell
# VULNERABLE: Following symlinks without validation
$Item = Get-Item -Path $UserPath
Get-Content -Path $Item.FullName

# SAFE: Check for symlinks
$Item = Get-Item -Path $UserPath
if ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw "Symbolic links not allowed"
}
$ResolvedPath = [System.IO.Path]::GetFullPath($Item.FullName)
# Also validate resolved path is within allowed directory
```

## Integration with Remediation Plan

### M1: CWE Coverage Expansion

**Recommendation**: Add path traversal family as a unified category:

```markdown
**[Path Traversal and File Access]**
- CWE-22: Path Traversal - Parent category for directory escape vulnerabilities (OWASP A01:2021)
- CWE-23: Relative Path Traversal - Attack using ../ sequences
- CWE-36: Absolute Path Traversal - Attack using absolute paths /etc/passwd
- CWE-73: External Control of File Name or Path - Root cause enabling path attacks (OWASP A03:2021)
- CWE-99: Resource Injection - Broader class containing file-based attacks
```

### M2: PowerShell Security Checklist

**Add Detection Patterns**:

1. `StartsWith()` without `GetFullPath()` normalization
2. `Join-Path` with unchecked user input (absolute path risk)
3. Missing symlink validation before file operations
4. Direct user input in `-Path` parameters

### M4: Feedback Loop Infrastructure

**Add Memory Tagging**:

```json
{
  "tags": ["path-traversal-family", "cwe-22", "cwe-23", "cwe-36", "cwe-73", "cwe-99"],
  "category": "file-access-control",
  "owasp": ["A01:2021", "A03:2021"]
}
```

### M5: Testing Framework

**Add Benchmark Test Cases**:

1. Relative traversal: `../../../etc/passwd`
2. Absolute path injection: `/etc/passwd`
3. Join-Path bypass: Absolute path as second argument
4. StartsWith bypass: `..` sequences before validation
5. Symlink following: Link to sensitive file

## Severity Calibration

Based on CVSS v3.1 and context:

| Scenario | Base Score | Context Modifier | Final Severity |
|----------|------------|------------------|----------------|
| Path traversal reading sensitive files | 7.5 (HIGH) | Remote service | CRITICAL (9.1) |
| Path traversal in local CLI tool | 7.5 (HIGH) | Local execution | HIGH (7.5) |
| Path traversal writing/deleting files | 9.1 (CRITICAL) | Any context | CRITICAL (9.1-10.0) |
| Limited traversal (single directory up) | 5.3 (MEDIUM) | Local CLI | MEDIUM (5.3) |

## Detection Methods

### Static Analysis

- Pattern matching for `StartsWith()` without `GetFullPath()`
- Data flow analysis: User input to file operations
- API usage: `Join-Path`, `Get-Content -Path`, `Set-Content -Path` with unchecked input

### Dynamic Analysis

- Fuzzing with `../` sequences
- Absolute path injection testing
- Symlink resolution testing

### Code Review Checklist

- [ ] All user-supplied file paths normalized with `GetFullPath()`
- [ ] Path containment validated AFTER normalization
- [ ] Absolute paths rejected or handled safely in `Join-Path`
- [ ] Symlink following explicitly handled
- [ ] Case-insensitive comparison on Windows paths

## References

### Primary Sources

- [CWE-699: Software Development View](https://cwe.mitre.org/data/definitions/699.html)
- [CWE-22: Path Traversal](https://cwe.mitre.org/data/definitions/22.html)
- [CWE-23: Relative Path Traversal](https://cwe.mitre.org/data/definitions/23.html)
- [CWE-36: Absolute Path Traversal](https://cwe.mitre.org/data/definitions/36.html)
- [CWE-73: External Control of File Name or Path](https://cwe.mitre.org/data/definitions/73.html)
- [CWE-99: Resource Injection](https://cwe.mitre.org/data/definitions/99.html)
- [OWASP Top 10:2021 A01 Broken Access Control](https://owasp.org/Top10/2021/A01_2021-Broken_Access_Control/)
- [OWASP Top 10:2021 A03 Injection](https://owasp.org/Top10/2021/A03_2021-Injection/)

### Project Context

- [Security Agent Detection Gaps Memory](.serena/memories/security-agent-vulnerability-detection-gaps.md)
- [Remediation Plan](.agents/planning/security-agent-detection-gaps-remediation.md)
- [PR #752 Security Report](.agents/security/SR-pr752-memory-system-foundation.md)

## Python and Shell Security Patterns

### Python Command Injection Prevention (CWE-78)

Based on 2024 CISA/OpenSSF guidance for secure subprocess usage:

#### Safe Pattern: List Arguments

```python
# RECOMMENDED: Pass command and arguments as list
subprocess.run(['git', 'diff', '--cached'], capture_output=True, check=True)
```

#### Safe Pattern: Use pathlib Instead of Shell Commands

| Task | Shell Command | Python Alternative |
|------|---------------|-------------------|
| List files | `ls -1 *.txt` | `Path.glob("*.txt")` |
| Recursive find | `find .` | `Path.rglob("*.txt")` |
| Check directory | `test -d` | `Path.is_dir()` |
| Copy files | `cp src dst` | `shutil.copy(src, dst)` |

#### Codebase Validation

The ai-agents Python files use subprocess SAFELY:

| File | Pattern | Status |
|------|---------|--------|
| `detect_infrastructure.py:90` | List arguments to subprocess.run | SAFE |
| `collect_metrics.py:100` | List arguments to subprocess.run | SAFE |

No unsafe patterns (shell=True, string concatenation) found in Python files.

### OWASP/CISA 2024 Guidance

Per CISA Secure by Design Alert (July 2024):

1. Use built-in library functions that separate commands from arguments
2. Avoid shell interpreters when possible
3. Prefer specialized modules (pathlib, shutil) over subprocess

**References**:

- [CISA OS Command Injection Alert](https://www.cisa.gov/resources-tools/resources/secure-design-alert-eliminating-os-command-injection-vulnerabilities)
- [OpenSSF Python Secure Coding Guide CWE-78](https://best.openssf.org/Secure-Coding-Guide-for-Python/CWE-707/CWE-78/)

## Codebase Security Scan Results

A comprehensive scan of PowerShell scripts in this repository identified 8 potential vulnerabilities across 4 additional CWE categories beyond path traversal.

### Additional CWEs Identified

#### CWE-94: Code Injection

**Definition**: The product constructs code segments using externally-influenced input without neutralizing special elements.

**Codebase Finding**: `scripts/lib/Install-Common.psm1:133`

```powershell
$ResolvedPath = $ExecutionContext.InvokeCommand.ExpandString($PathExpression)
```

**Risk**: MEDIUM. `ExpandString()` expands ALL variable references, including potentially untrusted ones. If `PathExpression` comes from external config, it enables variable injection.

**Mitigation**: Whitelist specific allowed variables ($HOME, $env:APPDATA) and reject expressions containing others.

#### CWE-1333: Inefficient Regular Expression Complexity (ReDoS)

**Definition**: Regular expressions with exponentially complex worst-case performance allowing denial of service.

**Codebase Finding**: `.claude/skills/security-detection/detect-infrastructure.ps1:71-83`

```powershell
function Test-Pattern {
    param([string]$FilePath, [string[]]$Patterns)
    foreach ($pattern in $Patterns) {
        if ($FilePath -match $pattern) { return $true }
    }
    return $false
}
```

**Risk**: HIGH if patterns come from external configuration. Malicious patterns with nested quantifiers cause catastrophic backtracking.

**Mitigation**: Use regex engines without backtracking, implement backtracking limits, or validate pattern complexity before use.

#### CWE-367: Time-of-check Time-of-use (TOCTOU) Race Condition

**Definition**: The resource state can change between security check and use.

**Codebase Finding**: `scripts/Sync-McpConfig.ps1:102-105`

```powershell
if ((Get-Item $SourcePath).LinkType) {
    Write-Error "Security: Source path is a symlink, which is not allowed"
    exit 1
}
# Gap here where symlink could be created
# ... then file operations on lines 109-110
```

**Risk**: LOW. Symlink could be swapped in between check and file operations.

**Mitigation**: Combine check and use operations atomically, or recheck immediately before each file operation.

#### CWE-295: Improper Certificate Validation

**Definition**: Software fails to properly validate digital certificates, enabling MITM attacks.

**Codebase Finding**: `scripts/install.ps1:82-84`

```powershell
$WebClient = New-Object System.Net.WebClient
$WebClient.DownloadFile("$BaseUrl/scripts/lib/Install-Common.psm1", "$LibDir/Install-Common.psm1")
```

**Risk**: LOW. Legacy `WebClient` does not validate certificates properly by default.

**Mitigation**: Use `Invoke-RestMethod` or `Invoke-WebRequest` which handle certificate validation correctly.

### Positive Security Practices Observed

The codebase demonstrates strong security patterns:

| Pattern | Location | Implementation |
|---------|----------|----------------|
| Path Traversal Prevention | `GitHubCore.psm1:102-145` | `Test-SafeFilePath` with `GetFullPath()` and `StartsWith()` |
| Path Containment | `Generate-Agents.Common.psm1:14-44` | `Test-PathWithinRoot` with directory separator appending |
| Input Validation | `GitHubCore.psm1:60-100` | Strict regex for GitHub owner/repo names |
| GraphQL Safety | `Invoke-PRMaintenance.ps1:316` | Variables passed via GraphQL parameters, not string interpolation |

### Vulnerability Summary Table

| File | Issue | CWE | Risk | Line(s) |
|------|-------|-----|------|---------|
| Install-Common.psm1 | ExpandString variable injection | CWE-94 | MEDIUM | 133 |
| detect-infrastructure.ps1 | Regex ReDoS potential | CWE-1333 | HIGH | 71-83 |
| Sync-McpConfig.ps1 | Symlink TOCTOU race | CWE-367 | LOW | 102-105 |
| New-Issue.ps1 | BodyFile lacks safe path check | CWE-22 | MEDIUM | 59-64 |
| install.ps1 | WebClient certificate validation | CWE-295 | LOW | 82-84 |
| Generate-Agents.ps1 | Config regex pattern injection | CWE-1333 | LOW | 215 |

### Remediation Plan Updates

Based on codebase findings, add to M1 (CWE Coverage Expansion):

```markdown
**[Code Execution and Injection]**
- CWE-94: Code Injection - Dynamic code generation from untrusted input (PowerShell: Invoke-Expression, ExpandString)

**[Availability and Resource Management]**
- CWE-1333: ReDoS - Regular expressions with exponential complexity enabling denial of service

**[Race Conditions]**
- CWE-367: TOCTOU - Security check invalidated before resource use

**[Authentication and Cryptography]**
- CWE-295: Improper Certificate Validation - Missing or incorrect TLS certificate checks
```

## Conclusions

1. **Unified Detection**: Treat path traversal CWEs (22, 23, 36, 73, 99) as a family requiring unified detection logic
2. **Root Cause Focus**: CWE-73 (External Control) is the enabling condition. Detecting CWE-73 catches all path traversal variants
3. **PowerShell Priority**: `GetFullPath()` normalization is the critical mitigation. Any `StartsWith()` without normalization is HIGH/CRITICAL
4. **OWASP Dual Mapping**: Path traversal maps to both A01 and A03, requiring detection in both access control and injection reviews
5. **Severity Escalation**: File write/delete operations escalate path traversal from HIGH to CRITICAL regardless of context
6. **Codebase Gaps**: Add CWE-94 (Code Injection), CWE-1333 (ReDoS), CWE-367 (TOCTOU), CWE-295 (Certificate Validation) to security agent prompt
7. **Existing Strengths**: `Test-SafeFilePath` and `Test-PathWithinRoot` patterns are well-implemented. Extend these patterns to all file operations
