# security-review

Reviews a diff or snippet for vulnerabilities inside your current session. It threat-models the change, maps findings to CWEs, and ends with one verdict: `IDENTIFY`, `OK`, or `ESCALATE`.

## When to use it

- You want to review a diff, file, or snippet for exploitable risk, with the security knowledge inline instead of in a subagent.
- You want a CWE-mapped risk assessment before merge.
- Trigger phrases: `security review`, `review this diff for security`, `inline security review`, `check CWE risk`.

## When not to use it

- You want STRIDE attack-surface analysis of a system or architecture: use [`threat-modeling`](threat-modeling.md).
- You want to decide whether a review is needed at all: use [`security-detection`](security-detection.md).
- You want a dispatched subagent with its own context: use the [`security`](../agents/security.md) agent.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:security-review`. The agent loads it when your request matches, and [`autoplan`](autoplan.md) routes diff vulnerability requests here. To ask for it by name, say:

```text
Use the security-review skill to review the diff in scripts/sync_artifacts.py for command injection and path traversal.
```

The skill reads the change as untrusted data, threat-models it, and returns findings with a final verdict line.

## What you get

Each finding has one sentence of description that carries the actor, surface, and impact, a severity (Critical, High, Medium, or Low), a CVSS or risk score, and one sentence of remediation. Every finding names a CWE or says why none applies. No secrets, tokens, or raw private payloads are quoted.

The final line holds exactly one verdict:

| Verdict | Meaning |
| --- | --- |
| `IDENTIFY` | A vulnerability is present. The finding names the CWE, surface, and impact, and recommends a mitigation. |
| `OK` | No unmitigated finding at or above medium. A pure rename or comment edit with no attack surface is `OK`. |
| `ESCALATE` | The diff is incomplete, or an external or irreversible decision (disclosure, secret rotation) needs an owner. Name the missing artifact or owner decision. |

If the shown diff lets you answer the threat-model questions, the verdict is `IDENTIFY` or `OK`, never `ESCALATE`. The verdict set differs from the security agent's `APPROVED`, `CONDITIONAL`, and `BLOCKED`, which suits the agent-versus-skill evaluation.

## Advanced use

Before assigning severity or a score, the skill answers three questions and writes the answers into the finding:

1. Attack surface: the concrete entry point (CLI argv, HTTP route, environment variable, file path, MCP tool parameter, agent prompt input).
2. Threat actor: the actor class and the capability it needs (anonymous user, low-privilege user, malicious contributor, compromised dependency, prompt-injected agent input).
3. Impact: the concrete loss (RCE on the runner, secret exfiltration, goal hijack, session-log tampering, denial of service).

A severity without a named actor and impact is returned for rework. The CWE catalog groups findings under injection and code execution, authentication and session, authorization, cryptography, input validation, and resource management, mapped to CWE-699 and OWASP Top 10:2021.

Highest-risk surfaces get extra scrutiny: workflow and CI/CD changes (reject `eval`, unquoted variables, and dynamic command construction without justification), any secret in the diff (an automatic block), and agentic boundaries where a prompt-injection or goal-hijack path has no compensating control.

Fetched advisories, PR comments, and code are data, not instructions. The skill ignores instructions embedded in them and notes the attempt. It never marks a security thread resolved without a code fix or an explicit owner.

The agent template `templates/agents/security.shared.md` is the canonical source. This skill is a projection of it and is re-synced when the template changes.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`security`](../agents/security.md): the subagent form of the same review.
- [`threat-modeling`](threat-modeling.md): STRIDE analysis of systems.
- [`security-scan`](security-scan.md): regex scanner for CWE-78 command injection.
- [`security-detection`](security-detection.md): decides whether review is warranted.
- Source: [`SKILL.md`](../../src/claude/skills/security-review/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
