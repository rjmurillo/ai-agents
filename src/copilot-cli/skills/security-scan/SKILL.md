---
name: security-scan
description: Detect CWE-78 (command injection) regex patterns in Python, PowerShell, Bash, and C# files before PR submission. CWE-22 is delegated to CodeQL; see Scope. Use when you ask "scan for command injection", "CWE-78 check before PR". Do NOT use to decide whether security review is warranted (use security-detection).
license: MIT
metadata:
  version: 2.0.0
  model: claude-sonnet-4-6
---

# Security Scan

Proactive vulnerability detection for command injection (CWE-78) before PR submission.

<!-- vendor-portability: declared. This skill cites .agents/analysis/closed-pr-reviewer-patterns-2026-02-08.md as the source for its detection patterns. It is a documentation citation only; scan_vulnerabilities.py scans the consumer's staged or specified files at runtime and does not read the .agents/ file. A vendored install without .agents/ loses the citation link, not the scan. Issue #2050. -->

## Scope

This skill detects **CWE-78 (command injection)** patterns only. The regex patterns target unambiguous shapes (`subprocess.run(..., shell=True)`, `eval(user_input)`, backtick command substitution, etc.) that produce reliable signal without taint analysis.

**CWE-22 (path traversal) is delegated to CodeQL.** The CodeQL workflow runs `python-security-extended.qls` and `actions-security-extended.qls` on every PR, authoritatively detecting CWE-22 across **Python and GitHub Actions** code (the two languages CodeQL supports for this repo per `codeql-config.yml`). PowerShell, Bash, and C# are NOT covered by CodeQL; for those languages, CWE-22 detection relies on code review and any future static analyzer adoption. Per the buy-vs-build framework analysis (issue #1843), maintaining a custom regex-based CWE-22 detector created false positives (PR #1841 added seven suppression annotations to silence them) without comparable coverage of real CWE-22 vectors that CodeQL catches in CI. Path-traversal checking is Context (table stakes security, not a competitive differentiator); CodeQL is the right tool for the languages it supports.

If a CWE-22 finding surfaces in CI from CodeQL, fix the underlying code or open an issue to triage. Do not add a regex-based CWE-22 check to this scanner.

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `scan for vulnerabilities` | scan_vulnerabilities.py on staged/specified files (CWE-78 only) |
| `check for command injection` | scan_vulnerabilities.py with CWE-78 focus |
| `check for path traversal` | NOT handled by this scanner. CWE-22 detection is delegated to CodeQL (see the CodeQL Analysis workflow, which runs python-security-extended.qls). |
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

## Scripts

| Script | Purpose | Exit codes |
|--------|---------|------------|
| `scripts/scan_vulnerabilities.py` | CWE-78 (command injection) regex scanner over staged, specified, or `--directory` files; supports `--format json`. CWE-22 is delegated to CodeQL; see Scope. | `0` no vulnerabilities; `1` scan error (file not found, etc.); `10` vulnerabilities detected. |

`scan_constants.py`, `scan_patterns.py`, and `scan_format.py` are helper modules imported by the scanner, not standalone CLIs.

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
# Command injection only (the only CWE this scanner detects)
python .claude/skills/security-scan/scripts/scan_vulnerabilities.py --cwe 78 --git-staged
```

`--cwe 22` is accepted for backward compatibility but produces no findings. The scanner emits a stderr warning pointing at CodeQL when invoked with `--cwe 22`. To check for path traversal, rely on the CodeQL workflow at `.github/workflows/codeql-analysis.yml`.

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
# security-scan: ignore CWE-78 - command validated by allow_list at line N
```

Suppressions are tracked in scan output for audit purposes. The mechanism only applies to CWE classes this scanner detects (CWE-78). For CWE-22, suppress at the CodeQL level using `lgtm` or `codeql[suppress]` comments (see CodeQL docs).

---

## Verification

After running security scan:

- [ ] All HIGH/CRITICAL CWE-78 findings addressed or documented
- [ ] No command injection patterns with dynamic input
- [ ] Variables quoted in shell scripts
- [ ] Input validation present before command operations
- [ ] Suppressions documented with justification
- [ ] CWE-22 path-traversal coverage verified separately via CodeQL CI run

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

- [CWE-78: OS Command Injection](https://cwe.mitre.org/data/definitions/78.html)
- [CWE-22: Path Traversal](https://cwe.mitre.org/data/definitions/22.html) (delegated to CodeQL; see Scope above)
- [OWASP Command Injection](https://owasp.org/www-community/attacks/Command_Injection)
- [Path Traversal Research (2025)](https://arxiv.org/abs/2505.20186)
- Analysis: `.agents/analysis/closed-pr-reviewer-patterns-2026-02-08.md`

---

## Extension Points

| Extension | How to Add |
|-----------|------------|
| New CWE-78 patterns | Add to `CWE78_PATTERNS` dict in scan_vulnerabilities.py |
| New CWE class detection | Do NOT add to this scanner. Configure CodeQL queries in `.github/codeql/codeql-config.yml` instead. The buy-vs-build analysis (issue #1843) established that CWE detection beyond CWE-78's narrow regex shapes belongs in CodeQL. |
| New language support | Add language detection and patterns |
| Custom severity rules | Modify severity calculation logic |
| Integration with other tools | Add output format adapters |
