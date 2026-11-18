# threat-modeling

Builds a structured threat model for a feature, component, or system. It uses the OWASP Four-Question Framework and STRIDE, and produces a threat matrix with risk ratings, mitigations, and a prioritized roadmap.

## When to use it

- You design a feature that handles sensitive data or authentication.
- You review an architecture for security weaknesses, or analyze an attack surface.
- You want to identify more attack vectors after a security incident, or prepare documents before an audit.
- Trigger phrases: `threat model`, `attack surface analysis`, `security architecture review`, `STRIDE analysis`, `what can go wrong`.

## When not to use it

- You want a risk review of one diff or snippet: use [`security-review`](security-review.md).
- You want to detect security-critical file changes in a PR: use [`security-detection`](security-detection.md).
- You want general project risks, not security threats: use [`pre-mortem`](pre-mortem.md).
- You want an agent to threat-model a pull request and return a risk verdict: use the [`security`](../agents/security.md) agent instead.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:threat-modeling`. The agent loads it when your request matches, and [`review`](review.md) invokes it when a change adds attack surface to an agent path. To ask for it by name, say:

```text
Use the threat-modeling skill to build a STRIDE threat model for the authentication service in src/auth.
```

The skill defines scope, draws the data flows and trust boundaries, applies STRIDE to each element, rates risk, and writes the model under `.project-toolkit/security/threat-models/`.

## What you get

| Input | Output | Destination |
| --- | --- | --- |
| Architecture diagram or description | Threat matrix with STRIDE categories | `.project-toolkit/security/threat-models/` |
| Component list | Trust boundary analysis | `.project-toolkit/security/threat-models/` |
| Data flow description | Data flow diagram threats | `.project-toolkit/security/threat-models/` |
| Prior threat model | Updated model with delta analysis | `.project-toolkit/security/threat-models/` |

Each threat entry has an element, a STRIDE category, an attack scenario, likelihood and impact with justification, a risk level (`Critical`, `High`, `Medium`, `Low`), mitigations with status, and residual risk. Risk is likelihood times impact on a 1 to 3 scale. The skill chooses one strategy per threat: mitigate, accept, transfer, or eliminate.

## Advanced use

The four phases map to the OWASP questions:

| Phase | OWASP question | Work |
| --- | --- | --- |
| 1. Scope and decompose | What are we working on? | Set scope (sprint, component, system, or enterprise), build a data flow diagram with external entities, processes, data stores, flows, and trust boundaries, and list assets. |
| 2. Threat identification | What can go wrong? | Apply STRIDE per element: spoofing, tampering, repudiation, information disclosure, denial of service, elevation of privilege. |
| 3. Mitigation strategy | What do we do about it? | Rate risk, choose a strategy, document mitigations with owners, generate a roadmap. |
| 4. Validation | Did we do a good job? | Run the validator, get peer review, schedule updates. |

Run the scripts from the root of a checkout of this repository:

```bash
uv run python .claude/skills/threat-modeling/scripts/generate_threat_matrix.py --scope "Authentication Service" --output .project-toolkit/security/threat-models/auth-threats.md
uv run python .claude/skills/threat-modeling/scripts/generate_mitigation_roadmap.py --input .project-toolkit/security/threat-models/auth-threats.md --output .project-toolkit/security/threat-models/auth-roadmap.md
uv run python .claude/skills/threat-modeling/scripts/validate_threat_model.py .project-toolkit/security/threat-models/auth-threats.md --json
```

| Script | Flags | Exit codes |
| --- | --- | --- |
| `generate_threat_matrix.py` | `--scope`, `--output` (both required) | 0 written, 1 generation failed |
| `generate_mitigation_roadmap.py` | `--input` or `-i`, `--output` or `-o` | 0 written, 1 input missing or unreadable, or generation failed |
| `validate_threat_model.py` | `path`, `--json` | 0 passed, 10 failed (not an ADR-035 code) |

The validator checks that every component has at least one threat, every trust boundary is crossed by a data flow, all STRIDE categories were considered for applicable elements, Critical and High risks have planned mitigations, and no threat is orphaned.

Update a threat model when features are added, the architecture changes, or an incident occurs. The source recommends a quarterly review. Search Serena memory for prior models before you start, and store a summary memory afterward. Write to Serena only from the checkout where the server started.

Deeper material is in [`advanced-analysis.md`](../../src/claude/skills/threat-modeling/references/advanced-analysis.md) (attack trees and kill chains), [`stride-methodology.md`](../../src/claude/skills/threat-modeling/references/stride-methodology.md), and [`risk-rating-guide.md`](../../src/claude/skills/threat-modeling/references/risk-rating-guide.md). The document template ships at [`templates/threat-model-template.md`](../../src/claude/skills/threat-modeling/templates/threat-model-template.md) in the skill.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`review`](review.md): invokes this skill for changes that add attack surface.
- [`security`](../agents/security.md): detailed vulnerability analysis.
- [`architect`](../agents/architect.md): reviews the threat model during design.
- [`codeql-scan`](codeql-scan.md): validates code against identified threats.
- [`adr-review`](adr-review.md): security review of architecture decisions.
- Source: [`SKILL.md`](../../src/claude/skills/threat-modeling/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
