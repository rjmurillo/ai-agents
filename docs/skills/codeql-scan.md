# codeql-scan

Runs CodeQL security scans on your Python and GitHub Actions code. It detects languages, caches databases, and writes SARIF results.

## When to use it

- You need static security analysis of Python or GitHub Actions code.
- [`security-scan`](security-scan.md) found issues or high-risk files and escalates to a full scan.
- [`review`](review.md) step 4d runs the CodeQL pre-step when the security axis is selected.
- Trigger phrases: `Run CodeQL scan`, `Check for vulnerabilities`, `Validate CodeQL configuration`, `Quick security scan`, `Scan for security issues`.

## When not to use it

- You want a fast pattern check for command injection before a PR: use [`security-scan`](security-scan.md).
- You want to know whether a change needs security review: use [`security-detection`](security-detection.md).

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:codeql-scan`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the codeql-scan skill to run a quick scan of this repository and list the findings by severity.
```

The agent runs the scan wrapper, then shows a console summary and the paths of the SARIF files.

## What you get

- SARIF files at `.codeql/results/<language>.sarif`, for IDE integration.
- A console summary of findings by severity.
- With `--format json`, a status object on stdout when the scan is skipped because `.codeql/` is missing.

| Exit code | Meaning |
| --- | --- |
| 0 | Success (no findings, or findings ignored). Also returned when `.codeql/` is missing and you did not pass `--ci` (skipped). |
| 1 | Findings detected (CI mode only). |
| 2 | Configuration invalid, or `.codeql/` missing with `--ci` (no scan ran). |
| 3 | Scan execution failed. |

## Advanced use

Run the wrapper from the root of a checkout of this repository:

```bash
uv run python .claude/skills/codeql-scan/scripts/invoke_codeql_scan.py --operation quick
```

| Flag | Meaning |
| --- | --- |
| `--operation` | `full`, `quick`, or `validate`. Default is `full`. |
| `--languages` | One or more of `python`, `actions`. Auto-detected when omitted. |
| `--ci` | CI mode: exit 1 on findings, exit 2 if `.codeql/` is missing. |
| `--format` | `console` (default) or `json`. |

| Operation | Use when | Typical time | Output |
| --- | --- | --- | --- |
| `full` | First scan, major changes, pre-PR validation | 30 to 60 seconds | SARIF and console |
| `quick` | Iterative development, minor changes | 10 to 20 seconds | SARIF and console |
| `validate` | Config changes, troubleshooting | under 5 seconds | Console only |

Use `--operation validate` before a scan to catch config errors early. Always check the exit code. To fix a timeout, scan one language with `--languages python`. To fix a stale cache, run a `full` scan.

The wrapper calls the core scripts in `.codeql/scripts/`: `install_codeql.py` (installs the CLI), `invoke_codeql_scan.py`, `test_codeql_config.py` (validates configuration), and `get_codeql_diagnostics.py` (health check with `console`, `json`, or `markdown` output). If the CLI is missing at `.codeql/cli/codeql`, run `install_codeql.py` first.

Before you finish a scan task, confirm the CLI is installed, the config validated, the wrapper exited 0, SARIF files exist, and you reviewed the findings. Address high and medium findings. Document or suppress low ones.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`security-scan`](security-scan.md): escalates to this skill for full SAST analysis.
- [`security-detection`](security-detection.md): identifies high-risk changes before a CodeQL scan.
- [`github`](github.md): reports CodeQL findings to PR reviews.
- Source: [`SKILL.md`](../../src/claude/skills/codeql-scan/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
