# security-scan

Scans Python, PowerShell, Bash, and C# files for command injection (CWE-78) patterns before you open a PR. It uses regex patterns for clear shapes, such as `subprocess.run(..., shell=True)` and `eval` on user input.

## When to use it

- You are preparing code for a PR and want to catch command injection first.
- Your code builds shell commands dynamically or turns user input into file operations.
- You want a pre-commit security gate.
- Trigger phrases: `scan for vulnerabilities`, `check for command injection`, `pre-PR security scan`, `run security scan`, `scan for command injection`, `CWE-78 check before PR`.

## When not to use it

- You want to decide whether a change needs security review: use [`security-detection`](security-detection.md).
- You want deep data-flow analysis or SARIF output: use [`codeql-scan`](codeql-scan.md).
- You want design-level STRIDE analysis: use [`threat-modeling`](threat-modeling.md).
- You want to check path traversal (CWE-22). CodeQL covers it for Python and GitHub Actions in CI. This scanner does not.
- You want a broader review of your local diff for vulnerabilities and exposed secrets: use [`pr-quality-security`](pr-quality-security.md) instead.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:security-scan`. The agent loads it when your request matches, and [`autoplan`](autoplan.md) routes command injection scan requests here. To ask for it by name, say:

```text
Use the security-scan skill to scan my staged files for command injection before I open the PR.
```

The skill runs the scanner and lists each finding with file, line, matched pattern, severity, and a remediation.

## What you get

Console output by default. With `--format json`, stdout carries exactly one JSON envelope on every exit, and stderr stays empty. The envelope's `exit_code` matches the process exit code.

| Exit code | Meaning |
| --- | --- |
| 0 | No vulnerabilities found, or nothing assessed. |
| 1 | Scan error, such as a file not found, an unsupported `--cwe`, or a rejected path. |
| 2 | Invalid command-line arguments. |
| 3 | Git could not list staged files. |
| 10 | Vulnerabilities detected. CI should fail. |

> [!WARNING]
> `files_scanned: 0` means the scanner assessed nothing: nothing was staged, or no named file was a supported language. That is zero coverage, not a clean result, even though the exit code is 0. A `--directory` scan that finds no supported files, or a call with no target, exits 1.

## Advanced use

Run the scanner from the root of a checkout of this repository:

```bash
uv run python .claude/skills/security-scan/scripts/scan_vulnerabilities.py --git-staged --format json
```

| Flag | Meaning |
| --- | --- |
| `files` | Files to scan. |
| `--git-staged` | Scan git staged files. |
| `--directory`, `-d` | Scan all supported files in a directory. |
| `--cwe` | Filter by CWE number. Only 78 is supported. `--cwe 22` is accepted but produces no findings, and the flag may be removed after 2026-08-01. |
| `--format`, `-f` | `console` or `json`. |
| `--output`, `-o` | Output file. Default is stdout. A rejected path is never written. |

Detected shapes by language:

| Language | Pattern | Risk |
| --- | --- | --- |
| Python | Subprocess or shell execution with formatted or concatenated user data | CRITICAL |
| Python | `shell=True` with user data | HIGH |
| PowerShell | `Invoke-Expression` with variable interpolation | CRITICAL |
| PowerShell | Dynamic command execution or `Start-Process` with unvalidated input | HIGH |
| Bash | `eval` with user input, command substitution with user data | CRITICAL |
| Bash | Unquoted variables in commands | MEDIUM |
| C# | `Process.Start` with a dynamic command, string interpolation in process arguments | HIGH |

In Bash, an unquoted here-document delimiter (`<<EOF`) makes the shell expand the body, so the scanner flags each `$var` inside. Quote the delimiter (`<<'EOF'`). The scanner then skips the body only when every reader is a known print or filter command such as `cat`, `echo`, `printf`, `grep`, `sed`, `awk`, or `jq`. A body piped to a shell, `ssh`, `sudo`, or `psql` is still scanned. This is a deliberate limit.

Suppress a false positive with an inline comment that gives a reason:

```text
# security-scan: ignore CWE-78 - command validated by allow_list at line N
```

Suppressions are tracked in the scan output. The mechanism covers CWE-78 only.

Recommended order: [`security-detection`](security-detection.md), then this scan, then [`codeql-scan`](codeql-scan.md) if it finds issues or high-risk files, then the [`security`](../agents/security.md) agent for flagged findings. The `references/` folder holds remediation detail, a PowerShell checklist, agent guardrails, dependency risk scoring, and a CWE catalog. Open one only when its topic applies, such as [`vulnerability-patterns.md`](../../src/claude/skills/security-scan/references/vulnerability-patterns.md).

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`security-detection`](security-detection.md): decides whether review is warranted.
- [`codeql-scan`](codeql-scan.md): full static analysis, including CWE-22.
- [`threat-modeling`](threat-modeling.md): design-level STRIDE analysis.
- [`security`](../agents/security.md): deep review of flagged findings.
- Source: [`SKILL.md`](../../src/claude/skills/security-scan/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
