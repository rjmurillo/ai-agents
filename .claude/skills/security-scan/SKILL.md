---
name: security-scan
description: Scan code content for CWE-22 (path traversal) and CWE-78 (command injection) vulnerabilities before PR submission. Lightweight pattern-based detection for Python, PowerShell, Bash, and C# files. Use when preparing code for review or as a pre-commit gate.
license: MIT
metadata:
  version: 1.0.0
  model: claude-sonnet-4-5
---

# Security Scan

Proactive vulnerability detection for common security issues before PR submission.

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `scan for vulnerabilities` | scan_vulnerabilities.py on staged/specified files |
| `check for path traversal` | scan_vulnerabilities.py with CWE-22 focus |
| `check for command injection` | scan_vulnerabilities.py with CWE-78 focus |
| `pre-PR security scan` | scan_vulnerabilities.py on staged files |
| `run security scan` | scan_vulnerabilities.py with full scan |

---

## When to Use

Use this skill when:

- Preparing code for PR submission (catch issues before review)
- Working with file path handling (user input to file operations)
- Building shell commands dynamically
- Integrating pre-commit security gates

Use **security-detection** instead when:

- Determining if a file needs security review (path-based routing)
- Triggering security agent involvement based on file types

Use **codeql-scan** instead when:

- Running comprehensive SAST analysis (30-60s full scan)
- Need deep data flow analysis beyond pattern matching
- CI pipeline integration requiring SARIF output

Use **threat-modeling** instead when:

- Performing design-level security analysis
- Creating STRIDE threat matrices
- Strategic security architecture review

---

## Quick Reference

| Input | Output | Performance |
|-------|--------|-------------|
| Staged files | JSON findings + console summary | 2-5s |
| Specific files | JSON findings + console summary | 1-3s |
| Directory scan | JSON findings + console summary | 5-15s |

---

## Available Scripts

| Script | Purpose |
|--------|---------|
| `scripts/scan_vulnerabilities.py` | Main scanner for CWE-22 and CWE-78 patterns |

---

## Usage

### Basic Scan (Staged Files)

```bash
python .claude/skills/security-scan/scripts/scan_vulnerabilities.py --git-staged
```

### Scan Specific Files

```bash
python .claude/skills/security-scan/scripts/scan_vulnerabilities.py path/to/file.py another/script.ps1
```

### Scan Directory

```bash
python .claude/skills/security-scan/scripts/scan_vulnerabilities.py --directory src/
```

### JSON Output (CI Integration)

```bash
python .claude/skills/security-scan/scripts/scan_vulnerabilities.py --git-staged --format json
```

### Specific CWE Focus

```bash
# Path traversal only
python .claude/skills/security-scan/scripts/scan_vulnerabilities.py --cwe 22 --git-staged

# Command injection only
python .claude/skills/security-scan/scripts/scan_vulnerabilities.py --cwe 78 --git-staged
```

---

## Output

### Console Output (Default)

When vulnerabilities are detected, the scanner outputs findings with file location, pattern matched, and severity. Each finding includes the specific code line and a recommendation for remediation.

### JSON Output (CI Mode)

Machine-readable JSON format including scan timestamp, files scanned, vulnerability details (CWE, file, line, code, severity, recommendation), and summary statistics.

---

## Exit Codes

| Code | Meaning | CI Behavior |
|------|---------|-------------|
| 0 | No vulnerabilities found | Pass |
| 1 | Scan error (file not found, etc.) | Fail |
| 10 | Vulnerabilities detected | Fail |

---

## Detected Patterns

### CWE-22: Path Traversal

| Language | Pattern | Risk |
|----------|---------|------|
| Python | Path join with user input without validation | HIGH |
| Python | File open with unvalidated path | HIGH |
| Python | pathlib.Path without containment check | HIGH |
| PowerShell | Join-Path with user input without validation | HIGH |
| PowerShell | Get-Content with unvalidated path | HIGH |
| Bash | File operations with unvalidated path variables | HIGH |
| Bash | Source command with external input | CRITICAL |
| C# | Path.Combine with user input without validation | HIGH |
| C# | File operations with unvalidated path | HIGH |

**Detection Heuristics**:

- Variable names suggesting user input: `user*`, `input*`, `param*`, `arg*`, `request*`
- Missing validation patterns before file operations
- Absence of `..` traversal checks
- Missing path canonicalization

### CWE-78: Command Injection

| Language | Pattern | Risk |
|----------|---------|------|
| Python | Subprocess with string formatting and user data | CRITICAL |
| Python | Shell command execution with concatenated input | CRITICAL |
| Python | Subprocess with shell=True and user data | HIGH |
| PowerShell | Invoke-Expression with variable interpolation | CRITICAL |
| PowerShell | Dynamic command execution with unvalidated input | HIGH |
| PowerShell | Start-Process with unvalidated arguments | HIGH |
| Bash | eval with user input | CRITICAL |
| Bash | Command substitution with user data | CRITICAL |
| Bash | Unquoted variables in commands | MEDIUM |
| C# | Process.Start with dynamic command | HIGH |
| C# | String interpolation in process arguments | HIGH |

**Detection Heuristics**:

- String interpolation/concatenation in command construction
- shell=True in subprocess calls
- Unquoted variable expansion in shell scripts
- Dynamic command building from external input

---

## Integration

### Pre-commit Hook

Add to `.githooks/pre-commit` to run security scan before commits (blocking mode).

### CI Integration

Add a workflow step to run the scanner with JSON output and upload results as artifacts.

### Workflow Integration

Recommended workflow order:

1. security-detection: Identify if security-relevant files changed
2. security-scan: Scan code content for CWE patterns (THIS SKILL)
3. codeql-scan: Full SAST analysis (if security-scan finds issues or high-risk files)
4. security agent: Deep review of flagged vulnerabilities

---

## Process

```text
                        Security Scan Workflow
                        ======================

     ┌─────────────────┐
     │  Collect Files  │ <- --git-staged, --directory, or explicit paths
     └────────┬────────┘
              │
              ▼
     ┌─────────────────┐
     │ Detect Language │ <- .py, .ps1, .sh, .cs, .bash
     └────────┬────────┘
              │
              ▼
     ┌─────────────────┐
     │ Apply CWE-22    │ <- Path traversal patterns by language
     │ Patterns        │
     └────────┬────────┘
              │
              ▼
     ┌─────────────────┐
     │ Apply CWE-78    │ <- Command injection patterns by language
     │ Patterns        │
     └────────┬────────┘
              │
              ▼
     ┌─────────────────┐
     │ Aggregate       │ <- Deduplicate, sort by severity
     │ Findings        │
     └────────┬────────┘
              │
              ▼
     ┌─────────────────┐
     │ Output Results  │ <- Console or JSON format
     └─────────────────┘
```

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Skipping scan before PR | Vulnerabilities caught in review waste cycles | Run scan before every PR submission |
| Ignoring MEDIUM severity | Can escalate to exploitable | Review all findings, document accepted risks |
| Only scanning changed files | Misses vulnerabilities in dependencies | Periodic full directory scans |
| Suppressing without documentation | Loses context for future audits | Document suppressions in code comments |
| Using this instead of codeql-scan for SAST | Pattern matching misses data flow issues | Use both: this for quick feedback, CodeQL for deep analysis |

---

## Suppression

To suppress false positives, add inline comments with justification:

```text
# security-scan: ignore CWE-22 - path validated by validate_upload_path()
```

Suppressions are tracked in scan output for audit purposes.

---

## Verification

After running security scan:

- [ ] All HIGH/CRITICAL findings addressed or documented
- [ ] No path traversal patterns with user input
- [ ] No command injection patterns with dynamic input
- [ ] Variables quoted in shell scripts
- [ ] Input validation present before file/command operations
- [ ] Suppressions documented with justification

---

## Related Skills

| Skill | Relationship |
|-------|--------------|
| `security-detection` | Detects which files need review (path-based routing) |
| `codeql-scan` | Full SAST analysis (heavyweight, CI-focused) |
| `threat-modeling` | Design-level STRIDE analysis |
| `analyze` | General code analysis with security focus option |

---

## References

- [CWE-22: Path Traversal](https://cwe.mitre.org/data/definitions/22.html)
- [CWE-78: OS Command Injection](https://cwe.mitre.org/data/definitions/78.html)
- [OWASP Command Injection](https://owasp.org/www-community/attacks/Command_Injection)
- [Path Traversal Research (2025)](https://arxiv.org/abs/2505.20186)
- Analysis: `.agents/analysis/closed-pr-reviewer-patterns-2026-02-08.md`

---

## Extension Points

| Extension | How to Add |
|-----------|------------|
| New CWE patterns | Add to `PATTERNS` dict in scan_vulnerabilities.py |
| New language support | Add language detection and patterns |
| Custom severity rules | Modify severity calculation logic |
| Integration with other tools | Add output format adapters |
