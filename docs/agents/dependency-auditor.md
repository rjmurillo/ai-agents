# dependency-auditor agent

The `dependency-auditor` agent scans your dependencies for known vulnerabilities, outdated versions, and deprecations. It hands back a structured report with severity levels. It reports and prioritizes. It does not fix.

## When to use it

- You want a weekly scan, such as Monday morning before the sprint starts.
- You are about to cut a release and want to gate it on zero Critical and High findings.
- You just did a major dependency bump and want to check for transitive regressions.

## When not to use it

- You want dependencies updated for you: the agent reports only, so make the change yourself or hand it to [`implementer`](implementer.md).
- You want a security review of source code: use [`security`](security.md) instead.
- You want unused dependencies removed from code: use [`janitor`](janitor.md) instead.

## Quick start

In Claude Code, start your prompt with the agent name:

```text
dependency-auditor: audit src/MyApp.sln for vulnerable, outdated, and deprecated packages
```

In GitHub Copilot CLI:

```bash
copilot --agent dependency-auditor --prompt "audit src/MyApp.sln for vulnerable, outdated, and deprecated packages"
```

In VS Code or Visual Studio Copilot Chat:

```text
@dependency-auditor audit src/MyApp.sln for vulnerable, outdated, and deprecated packages
```

## What you get

A Markdown report named "Dependency Audit Report" with these parts:

- The date, the ecosystems scanned, and the ecosystems skipped with the reason.
- A summary table with counts by severity.
- A table of Critical and High findings: package, current version, fixed-in version, CVE, CVSS, and ecosystem.
- The top 10 outdated packages by staleness.
- A table of deprecated packages with the reason and an alternative.

Severity levels:

| Severity | Criteria | Action |
| --- | --- | --- |
| Critical | CVE with CVSS 9.0 or higher, or known-exploited (CISA KEV) | Block release; fix immediately |
| High | CVE with CVSS 7.0 to 8.9, or deprecated with no migration path | Fix before next release |
| Medium | CVE with CVSS 4.0 to 6.9, or outdated by 2 or more major versions | Schedule update |
| Low | Outdated by 1 minor or patch, or deprecated with a clear migration | Informational |

Exit signals:

| Code | Meaning |
| --- | --- |
| 0 | No Critical or High findings |
| 1 | At least one Critical or High finding (a gate signal for CI and release workflows) |
| 3 | At least one ecosystem was detected and every detected ecosystem failed to scan |

Partial scan failures still exit 0 or 1 based on findings.

## Advanced use

The agent walks the repository root for markers: `*.sln`, `*.csproj`, [`package.json`](../../package.json), [`pyproject.toml`](../../pyproject.toml), `requirements*.txt`, and `Cargo.toml`. It skips an ecosystem silently when no manifest or lockfile exists. It fails only on a scan error inside a detected ecosystem, and one ecosystem failing does not abort the others.

| Ecosystem | Commands |
| --- | --- |
| .NET (primary) | `dotnet list package --vulnerable --include-transitive`, `dotnet list package --outdated`, `dotnet list package --deprecated` |
| npm | `npm audit --json`, `npm outdated --json` |
| pip or uv | `pip-audit --format json`, `uv pip list --outdated --format json` (falls back to `pip list --outdated --format json`) |
| cargo | `cargo audit --json`, `cargo outdated --root-deps-only` |

Rules the agent follows:

- Scan the `.sln` file when one exists. Scanning single projects misses transitive dependencies resolved at solution level.
- Keep `--include-transitive` on the vulnerability scan. A direct dependency can be clean while its transitive tree carries a CVE.
- Do not treat "outdated" as "vulnerable". Staleness is a hygiene signal, not a security signal.
- Do not auto-merge or auto-update. The maintainer decides.

A multi-step prompt:

```text
dependency-auditor: scan every .sln and package.json in this repo, list ecosystems skipped, and tell me whether the release gate passes (exit 0) or fails (exit 1).
```

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| VS Code and Visual Studio | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`security`](security.md): reviews source code for security risk.
- [`janitor`](janitor.md): removes unused dependencies from code.
- [`devops`](devops.md): wires the scan into CI and scheduled workflows.
- Source template: [`dependency-auditor.shared.md`](../../templates/agents/dependency-auditor.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)
