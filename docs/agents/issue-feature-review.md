# issue-feature-review agent

The `issue-feature-review` agent reviews a GitHub feature request with constructive skepticism. It summarizes the ask, weighs user impact and cost, flags unknowns, and hands back one recommendation with next steps.

## When to use it

- A feature request or bug report arrives and you need to triage it.
- You want a recommendation on whether to proceed, defer, or decline.
- You want unknowns labeled so a maintainer knows what to research.

## When not to use it

- You need deep research on the topic: use [`analyst`](analyst.md) instead.
- You need an epic prioritized against others: use [`roadmap`](roadmap.md) instead.
- You need the accepted work scheduled: use [`milestone-planner`](milestone-planner.md) instead.

## Quick start

In Claude Code, start your prompt with the agent name:

```text
issue-feature-review: review this request. Title: "Add dry-run flag to export_report.py". Body: users want to preview what the script would export.
```

In GitHub Copilot CLI:

```bash
copilot --agent issue-feature-review --prompt "review this request. Title: 'Add dry-run flag to export_report.py'. Body: users want to preview what the script would export."
```

In VS Code or Visual Studio Copilot Chat:

```text
@issue-feature-review review this request. Title: "Add dry-run flag to export_report.py". Body: users want to preview what the script would export.
```

## What you get

A fixed Markdown layout:

- Thank You: one or two sentences to the submitter.
- Summary: two or three sentences.
- Evaluation: a table with User Impact, Implementation, Maintenance, Alignment, and Trade-offs. Each row has an assessment and a confidence of High, Medium, Low, or Unknown.
- Research Findings: what the agent could determine, and what needs manual research.
- Questions for Submitter: only when needed.
- Recommendation: one line, `RECOMMENDATION:` followed by one of `PROCEED`, `DEFER`, `REQUEST_EVIDENCE`, `NEEDS_RESEARCH`, or `DECLINE`, with a one or two sentence rationale.
- Suggested Actions: assignees, labels, milestone, and next steps.

## Advanced use

Depth matches the request. A standard request gets a quick evaluation. A strategic one gets its premises challenged. A vague one gets pushback.

| Situation | Recommendation |
| --- | --- |
| Standard feature with user demand | `PROCEED` or `DEFER` by priority |
| Bug report with clear symptoms | `PROCEED` with a severity label |
| Ambiguous user need | `NEEDS_RESEARCH` or `REQUEST_EVIDENCE` |
| Internal request with no external validation | `REQUEST_EVIDENCE` |
| Duplicates an existing feature | `DECLINE` with a pointer |
| Technically infeasible | `DECLINE` with the specific blocker |
| Strategic direction conflict | `NEEDS_RESEARCH`, flagged to `architect` |

Rules the agent keeps:

- It does not fabricate data. When it cannot verify something, it writes `UNKNOWN - requires manual research by maintainer` and still gives a confidence-calibrated recommendation.
- It uses repository and GitHub issue context only. It does not browse the web.
- It asks specific questions, never "Can you provide more details?"
- It recommends `PROCEED` when evidence supports it and does not default to `DEFER`.

The output format mirrors `.github/prompts/issue-feature-review.md` so on-demand reviewers return the same shape.

The agent cannot delegate. It returns the recommendation with confidence, assignment suggestions, and a path to related research. When an orchestrator delegated the task, it adds a next step: `PROCEED` goes to `milestone-planner`, `NEEDS_RESEARCH` goes to `analyst`, a strategic conflict goes to `architect`, and `REQUEST_EVIDENCE` waits for the submitter.

A multi-step prompt:

```text
issue-feature-review: review issue 42 using only the issue body and repository files, label every unknown, and give the recommendation with the next agent to run.
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

- [`analyst`](analyst.md): researches requests that need more evidence.
- [`architect`](architect.md): reviews strategic direction conflicts.
- [`milestone-planner`](milestone-planner.md): schedules accepted requests.
- [`roadmap`](roadmap.md): prioritizes epics across requests.
- Source template: [`issue-feature-review.shared.md`](../../templates/agents/issue-feature-review.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)
