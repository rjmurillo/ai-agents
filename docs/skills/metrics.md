# metrics

Collects agent usage metrics from git history and turns them into a summary, Markdown, or JSON report. It also reports where new GitHub issues came from and tracks how old defects were introduced, found, and fixed.

## When to use it

- You want to measure agent adoption or system health over a time window.
- You want a periodic dashboard, such as a weekly or monthly report.
- You want to check whether agent use is balanced across agent types, or whether infrastructure changes got a security review.
- Trigger phrases: `collect agent metrics`, `generate metrics dashboard`, `weekly metrics report`, `check agent adoption rate`, `export metrics as JSON`.

## When not to use it

- You are investigating one commit's agent attribution or one CI run: read the git log or the run directly.

## Quick start

This skill is not a front door, so you rarely start it yourself. In Claude Code you can still type `/project-toolkit:metrics`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the metrics skill to collect agent metrics for the last 7 days and give me a Markdown report.
```

The skill runs `collect_metrics.py` for that window and reports the four metrics it collects. State the window, because the default is 30 days.

## What you get

| Metric | What it measures | Target |
| --- | --- | --- |
| Metric 1: Invocation Rate | Agent usage distribution | Proportional to task types |
| Metric 2: Agent Coverage | Share of commits with agent involvement | 50% |
| Metric 4: Infrastructure Review | Share of infrastructure changes with security review | 100% |
| Metric 5: Usage Distribution | Agent utilization patterns | Balanced distribution |

Output formats: `summary` (default, human-readable), `markdown` (for dashboards; can be saved under `.project-toolkit/metrics/`), and `json` (for automation and CI). Agent coverage of exactly 0% usually means the detection patterns do not match your commit message conventions.

## Advanced use

The skill ships three scripts in its own directory. From the root of a checkout of this repository:

```bash
uv run python .claude/skills/metrics/collect_metrics.py --since 7 --output markdown
uv run python .claude/skills/metrics/backlog_provenance.py --days 7
uv run python .claude/skills/metrics/defect_lineage.py --help
```

`collect_metrics.py` flags: `--since DAYS`, `--output summary|markdown|json`, `--repo-path`. Always set `--since` explicitly, and compare only like windows. It detects agents by name in commit messages, `Reviewed by:` lines, and `agent:` tags. It marks infrastructure commits by path patterns such as workflows, Dockerfiles, Terraform files, and lefthook configs.

**Backlog provenance.** `backlog_provenance.py` is a read-only report on issues created in a UTC window. It buckets each issue as `human-only`, `agent-only`, `conflict`, or `unknown` from the `source:human` and `source:agent` labels. It also reports two labeled heuristics: machinery share and bursts. It never files, labels, or closes an issue. Flags: `--owner`, `--repo`, `--days`, `--until` (exclusive UTC timestamp), and `--output-format markdown|json`. A failed or malformed page exits `3` and prints no partial report.

**Defect lineage.** `defect_lineage.py` keeps one JSON record per reviewed defect chain, so a later fix does not erase the evidence of a review race. It has three subcommands:

| Subcommand | Does |
| --- | --- |
| `check <paths>` | Validates records and rejects contradictions, such as a repair merged before detection |
| `report <paths>` | Prints records grouped into live, unverified, historical, and observation buckets |
| `recheck <record> [--rev REV] [--write]` | Reads the record's path at a revision and updates its status history |

Status is `CURRENT`, `FIXED`, `REVERTED`, `SUPERSEDED`, or `UNVERIFIED`. A missing file gives `UNVERIFIED`, never `FIXED`. `--rev` must be a branch, tag, or SHA; `HEAD~1` is rejected. `--root` belongs to the top-level parser, so put it before the subcommand. Exit codes: `0` ok, `1` invalid record, `2` bad path, JSON, or argument, `3` git cannot run or the revision does not resolve.

A weekly workflow in the repository, `agent-metrics.yml`, runs collection for the previous 7 days and opens a PR with the report. The skill runs on the `haiku` model tier.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- Source: [`SKILL.md`](../../src/claude/skills/metrics/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
