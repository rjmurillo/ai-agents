# security agent

The `security` agent reviews changes with a defense-first mindset. It threat-models a change, scores risk with evidence, and gates security-relevant pull requests with a verdict of `APPROVED`, `CONDITIONAL`, or `BLOCKED`.

## When to use it

- You are about to ship a change that touches authentication, secrets, input handling, code execution, or CI/CD.
- You need a threat model or a security report for a feature.
- A change modifies `.github/workflows/`, hook configuration, or files matching security paths such as `**/Auth/**`, `*.env*`, or `**/token*`.
- You need post-implementation verification (PIV) after the implementer finished a security-relevant change.
- A planner needs the security impact of a feature.

## When not to use it

- You want a dependency scan for vulnerable or outdated packages: use [`dependency-auditor`](dependency-auditor.md) instead.
- You want fixes applied: use [`implementer`](implementer.md) instead.
- You want a pattern scan for command injection: use the [`security-scan`](../skills/security-scan.md) skill instead.
- You want to decide whether a security review is warranted: use the [`security-detection`](../skills/security-detection.md) skill instead.
- You want a STRIDE threat model of a system you describe, in your current session: use the [`threat-modeling`](../skills/threat-modeling.md) skill instead.

## Quick start

> [!NOTE]
> In Claude Code, this agent's GitHub tools need a GitHub MCP server, which the plugin does not provide. Without one, the agent still runs but cannot read pull requests or issues. See [GitHub MCP prerequisite](../installation.md#github-mcp-prerequisite).

In Claude Code, start your prompt with the agent name:

```text
security: review PR 123 for security issues, with focus on any shell command construction
```

In GitHub Copilot CLI:

```bash
copilot --agent security --prompt "review PR 123 for security issues, with focus on any shell command construction"
```

In VS Code or Visual Studio Copilot Chat:

```text
@security review PR 123 for security issues, with focus on any shell command construction
```

## What you get

Every review ends with one verdict, and the verdict names its pinned scope: the SHA, the PR number, or the diff artifact path, plus the file count.

| Verdict | When |
| --- | --- |
| `APPROVED` | All HIGH and CRITICAL findings are addressed, MEDIUM findings have documented mitigations or accepted-risk reasons, and no secrets are present. |
| `CONDITIONAL` | At most 3 MEDIUM findings remain open with documented mitigations. The verdict names each and flags it to the owner. |
| `BLOCKED` | A HIGH or CRITICAL finding is unaddressed, a secret is in the diff, a CWE-22, CWE-77, or CWE-78 pattern is unmitigated, an agentic-security boundary is violated without a compensating control, or more than 3 MEDIUM findings need deferred work. |

If the diff is incomplete, the agent returns `[BLOCKED] Cannot evaluate: <specific missing artifact>`.

Files it writes under `.project-toolkit/security/`:

| File | Content |
| --- | --- |
| `SR-NNN-[scope].md` | A security report |
| `TM-NNN-[feature].md` | A threat model |
| `PIV-[feature].md` | A post-implementation verification |

For planning it writes `.project-toolkit/planning/impact-analysis-security-[feature].md`.

Reports are capped: each finding is one sentence, a severity, a CVSS or risk score, and a one-sentence fix. A report has at most 10 findings (grouped by root cause beyond that) and at most 5 recommendations. Findings carry CWE references, file locations, and line numbers.

## Advanced use

The agent has no shell on any surface. It reads a pinned snapshot through the GitHub read tools (`pull_request_read` with `get_diff`, `get_commit`, `list_commits`, `get_file_contents`, and the scanning alert tools), or it reads a diff artifact you supply. An artifact must be a complete snapshot: `git diff HEAD` plus the content of every untracked file the change adds. The agent does not assess a partial changeset. It does not delegate the review to another agent, a hook, or a skill.

Because it cannot run commands, the agent asks you or the implementer to run CI-equivalent security checks, such as hook configuration validation and secret scans, and it treats a missing result as an unmet PIV item. It never reports a check as passed that it did not see.

Before it assigns a severity it answers three questions: the attack surface, the threat actor, and the impact. A severity without a named actor and impact goes back for rework.

Scope coverage: the CWE-699 categories, OWASP Top 10:2021, and the OWASP Top 10 for Agentic Applications (2026, ASI01 to ASI10). It also does secret detection, a code quality audit from a security view (files over 500 lines, tight coupling), and attack surface mapping.

All pull requests require security review. Changes to workflow files get the highest scrutiny. The agent checks for existing hardened utilities first and fails any `eval`, unquoted variable, or dynamic command construction that lacks a justification and mitigation.

PIV is a blocking gate. The orchestrator must route to `security` after implementation when changed files match trigger patterns, and must not create the PR while the agent returns `BLOCKED`.

Reference files in the `security-scan` skill's `references/` folder: `security-cwe-catalog.md`, `security-impact-analysis.md`, `security-piv-ci-checks.md`, `powershell-security-checklist.md`, `dependency-risk-scoring.md`, and `threat-model-template.md`. New dependencies are scored with a weighted matrix of maintenance, popularity, security history, lock-in, and license.

External actions, such as disclosure, secret rotation, blocking deploys, or vendor contact, wait for your approval. The agent cannot delegate. Handoffs:

| Target | When | Purpose |
| --- | --- | --- |
| `implementer` | Security fix needed | Remediation |
| `devops` | Pipeline security | Infrastructure hardening |
| `architect` | Design-level change | Security architecture |
| `critic` | Risk assessment | Validate the threat model |

A multi-step prompt:

```text
security: run post-implementation verification for the token-refresh change on PR 123, check each planned control against the diff, list unmet PIV items I must run, and write PIV-token-refresh.md with a verdict.
```

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| VS Code and Visual Studio | Yes |
| Codex | No |
| Cursor | No |
| Muse | No |

Codex and Muse cannot limit an agent's tools, so the build leaves this agent out. It is not shipped on Cursor.

## Related

- [`implementer`](implementer.md): applies the remediation.
- [`devops`](devops.md): hardens pipelines.
- [`dependency-auditor`](dependency-auditor.md): scans package risk.
- [`critic`](critic.md): validates a threat model.
- [`security-scan`](../skills/security-scan.md): scans for CWE-78 patterns and holds the reference files.
- [`threat-modeling`](../skills/threat-modeling.md): the skill for threat models.
- Source template: [`security.shared.md`](../../templates/agents/security.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)
