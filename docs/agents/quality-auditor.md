# quality-auditor agent

The `quality-auditor` agent grades product domains across six architectural layers: agents, skills, scripts, tests, docs, and workflows. It hands back a report with letter grades, gap counts, and trends.

## When to use it

- You want a repository-wide quality audit or an audit of named domains.
- You want A to F domain grades and trend tracking against the previous run.
- You want to know which domains need attention first.

## When not to use it

- You want the skill form of the same grading: use the [`quality-grades`](../skills/quality-grades.md) skill instead.
- You want a maintainability score for a single file: use the [`code-qualities-assessment`](../skills/code-qualities-assessment.md) skill instead.
- You want a review before merge: use the [`review`](../skills/review.md) skill instead.

## Quick start

In Claude Code, start your prompt with the agent name:

```text
quality-auditor: grade the agents and skills domains and compare against the last run
```

In GitHub Copilot CLI:

```bash
copilot --agent quality-auditor --prompt "grade the agents and skills domains and compare against the last run"
```

In VS Code or Visual Studio Copilot Chat:

```text
@quality-auditor grade the agents and skills domains and compare against the last run
```

Omit the domain names for a full scan.

## What you get

A report per domain in this layout:

```text
## Domain: {name}
Overall: {grade} ({score}/100) ({trend})

| Layer | Grade | Score | Files | Gaps |
|-------|-------|-------|-------|------|
```

Grades are letters with numeric scores, such as "B (78/100)". The report carries gap counts by severity and trend indicators with direction and magnitude. The agent can save a JSON copy for trend comparison.

## Advanced use

The agent works in four phases:

1. Discovery: run the `grade_domains.py` script from the `quality-grades` skill to detect domains. If detection missed one, rerun with `--domains` and the complete list. The flag replaces auto-detection.
2. Grading: rerun with `--format json --output <path>` to persist results, and review grades for accuracy.
3. Reporting: write a Markdown report, highlight domains with critical gaps, and compare against the previous run.
4. Recommendations: prioritize domains graded D or F, list critical gaps first, and suggest a specific action for each gap.

Boundaries the agent keeps:

- It grades on structural evidence, not opinion.
- It does not modify code or files during an audit.
- It reports gaps as observations, not prescriptions.
- It tracks trends only when previous data exists.
- It grades rules, skills, and agents as executable artifacts using the `code-qualities-assessment` skill.

The agent can search memory with the Memory Router and write memories through Serena, but only from the checkout Serena started in. In a linked worktree it returns the change to the parent session instead.

A multi-step prompt:

```text
quality-auditor: run a full scan, save JSON output, list every domain graded D or F with its critical gaps, and suggest one action per gap.
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

- [`quality-grades`](../skills/quality-grades.md): the skill form of this audit.
- [`code-qualities-assessment`](../skills/code-qualities-assessment.md): scores one file for maintainability.
- [`review`](../skills/review.md): reviews a change before merge.
- Source template: [`quality-auditor.shared.md`](../../templates/agents/quality-auditor.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)
