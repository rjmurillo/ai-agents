# analyst agent

The `analyst` agent investigates before you implement. It surfaces root causes, unknowns, and dependencies, and hands back structured findings with an evidence pointer on every claim. It never changes code.

## When to use it

- You have a bug or incident with symptoms and need ranked hypotheses.
- You have a research question with a known scope and need a comparison with trade-offs.
- You need an impact assessment, requirements discovery, or hypothesis validation.
- You want pattern research on the codebase before a design decision.

## When not to use it

- You need the fix written: use [`implementer`](implementer.md) instead.
- You need a design decision: use [`architect`](architect.md) instead.
- You need shell commands run, such as git, builds, or tests: the agent has no shell, so the orchestrator runs them and passes the output.
- You need a plan validated: use [`critic`](critic.md) instead.

## Quick start

> [!NOTE]
> In Claude Code, this agent's GitHub tools need a GitHub MCP server, which the plugin does not provide. Without one, the agent still runs but cannot read pull requests or issues. See [GitHub MCP prerequisite](../installation.md#github-mcp-prerequisite).

In Claude Code, start your prompt with the agent name:

```text
analyst: find why the discount check in src/billing/checkout.py returns the wrong total for an expired coupon
```

In GitHub Copilot CLI:

```bash
copilot --agent analyst --prompt "find why the discount check in src/billing/checkout.py returns the wrong total for an expired coupon"
```

In VS Code or Visual Studio Copilot Chat:

```text
@analyst find why the discount check in src/billing/checkout.py returns the wrong total for an expired coupon
```

## What you get

A response with this layout. The agent writes no files. The orchestrator persists the findings if needed.

```text
# Investigation: [Topic]
## Problem Framing
## Hypotheses
## Evidence
## Findings
## Root Cause
## Recommendation
## Open Questions
```

It also reports a confidence level of HIGH, MEDIUM, or LOW with reasoning. Length caps: each finding is one sentence with a `file:line` pointer, at most 7 findings, at most 5 summary bullets, at most 7 plan steps, and the top 3 hypotheses.

## Advanced use

Every finding carries an evidence level:

| Level | Source |
| --- | --- |
| 1 | Grep output in this session (Glob lists count as Level 1) |
| 2 | File content read in this session |
| 3 | External documentation fetched in this session |
| 4 | Training knowledge. Never published. It moves to Open Questions or gets removed. |

The agent states what would falsify each claim and prefers the simplest explanation. Unknown is a finding: if the root cause needs data it cannot reach, it says what data would resolve it.

Tools are read-only: `Read`, `Grep`, `Glob`, Context7 and DeepWiki lookups, and Serena symbol and memory reads. It has no shell, no web, and no write tools. It reads GitHub context through `issue_read`, `pull_request_read`, `get_workflow_run`, `get_job_logs`, `list_workflow_runs`, `get_file_contents`, and `list_commits`. If one of those tools is not registered and the delegation gave no pre-fetched text, it returns `[BLOCKED]` with the missing context list and halts.

Before it reports PR findings it checks PR identity: repository, head ref, head SHA, and merge commit from the API must match any supplied values. A mismatch stops the analysis. Without a grounding record from the orchestrator, findings are labeled `UNVERIFIED`, never `CURRENT`.

Content returned by tools is data. The agent ignores embedded instructions and reports them.

Handoffs: `architect` for design decisions, `milestone-planner` for planning, `implementer` for fixes with a clear root cause, and `critic` for hypothesis validation. It cannot delegate.

A multi-step prompt:

```text
analyst: investigate PR 123. Read the PR with pull_request_read, rank the top 3 hypotheses for the failing check, tag each finding with its evidence level, and list what the orchestrator must run for me.
```

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| VS Code and Visual Studio | Yes |
| Codex | No |
| Cursor | Yes |
| Muse | No |

Codex and Muse cannot limit an agent's tools, so the build leaves this agent out.

## Related

- [`architect`](architect.md): makes the design decision from your findings.
- [`milestone-planner`](milestone-planner.md): plans the implementation.
- [`implementer`](implementer.md): fixes causes you confirmed.
- [`critic`](critic.md): validates hypotheses.
- [`orchestrator`](orchestrator.md): runs shell commands and pre-fetches context for this agent.
- Source template: [`analyst.shared.md`](../../templates/agents/analyst.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)
