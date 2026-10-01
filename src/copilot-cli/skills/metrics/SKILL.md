---
name: metrics
description: Collect agent usage metrics from git history and generate health reports. Use when measuring agent adoption, reviewing system health, or producing periodic dashboards. Collects Invocation Rate, Coverage, Infrastructure Review, and Usage Distribution. Use when you say "collect agent metrics", "generate metrics dashboard", or "weekly metrics report".
license: MIT
metadata:
  routing:
    role: explicit-only
    invoker: user
    trigger: a user asks to collect agent usage metrics
    user-facing: true
    rationale: Automatic routing would be noisy. Usage collection is an operator task, and inbound matches are the common word metrics in unrelated prose.
version: 1.0.0
---

# Agent Metrics Collection Utility

## Purpose

This utility collects and reports metrics on agent usage from git history. It collects 4 of the metrics defined in `docs/agent-metrics.md` (Invocation Rate, Coverage, Infrastructure Review, Usage Distribution) for measuring agent system health, effectiveness, and adoption.

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `collect agent metrics` | Run collect_metrics.py with default 30-day window |
| `generate metrics dashboard` | Run with markdown output for reporting |
| `check agent adoption rate` | Run and highlight Metric 2 (agent coverage) |
| `weekly metrics report` | Run with 7-day window, markdown output |
| `export metrics as JSON` | Run with JSON output for automation |

---

## When to Use

Use this skill when:

- Measuring agent system health or adoption trends
- Producing periodic dashboards or reports
- Evaluating whether agent usage is balanced across types
- Checking infrastructure review coverage

Use manual git log inspection instead when:

- Investigating a single commit's agent attribution
- Debugging a specific CI run's metrics workflow

---

## Process

1. Run the metrics collection script for the desired time range
2. Review generated reports for agent usage patterns
3. Identify trends and anomalies in adoption metrics

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Running without specifying time window | Default 30 days may not match your intent | Use --since with explicit day count |
| Comparing metrics across different time windows | Misleading trends | Normalize to same window size |
| Ignoring zero agent coverage | Indicates broken detection patterns | Verify commit message conventions match patterns |
| Manual commit counting | Error-prone, misses patterns | Use the script for consistent detection |
| Storing JSON output without markdown | Loses human-readable context | Generate both formats for archival |

---

## Verification

After execution:

- [ ] Script exits with code 0
- [ ] Output contains all 4 collected metrics (Invocation Rate, Coverage, Infrastructure Review, Distribution)
- [ ] Agent coverage percentage is plausible (not 0% unless truly no agent commits)
- [ ] Time window matches intended period
- [ ] For markdown output: report file created at expected path

---

## Available Scripts

| Script | Platform | Usage |
|--------|----------|-------|
| `collect_metrics.py` | Python 3.8+ | Cross-platform |
| `backlog_provenance.py` | Python 3.10+, `gh` | Read-only issue provenance report |

## Quick Start

```bash
# Basic usage (30 days, summary output)
python .claude/skills/metrics/collect_metrics.py

# Last 90 days as markdown
python .claude/skills/metrics/collect_metrics.py --since 90 --output markdown

# JSON output for automation
python .claude/skills/metrics/collect_metrics.py --output json

# Backlog provenance of issues created in the last 7 days (Markdown)
SCRIPTS_DIR="${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/metrics"
python "$SCRIPTS_DIR/backlog_provenance.py" --days 7

# Same report as JSON, for an explicit UTC interval ending 2026-09-29 (exclusive)
python "$SCRIPTS_DIR/backlog_provenance.py" --days 29 --until 2026-09-29T00:00:00Z --output-format json
```

## Metrics Collected

The utility collects the following metrics:

| Metric | Description | Target |
|--------|-------------|--------|
| Metric 1: Invocation Rate | Agent usage distribution | Proportional to task types |
| Metric 2: Agent Coverage | % of commits with agent involvement | 50% |
| Metric 4: Infrastructure Review | % of infra changes with security review | 100% |
| Metric 5: Usage Distribution | Agent utilization patterns | Balanced distribution |

## Backlog Provenance

`backlog_provenance.py` is a read-only diagnostic for epic #5698. It reads every
issue created in an explicit UTC interval and reports the split by recorded
`source:human` and `source:agent` label, plus two labeled heuristics. It does not
score productivity, and it never files, labels, or closes an issue.

- Buckets are mutually exclusive: `human-only`, `agent-only`, `conflict` (both labels), `unknown` (neither).
- Labels record provenance. They do not verify who selected the work.
- Machinery share matches a whole-word title term or the `area-validation` label. Bursts are 3 or more issues by one login within 10 minutes of the first. Both are heuristics, not causal attribution.
- The read pages until an empty page. Any failed or malformed page exits 3 and no partial report prints. Pull requests are excluded and issues are deduplicated by number.
- Markdown is the default on every terminal and redirect. Empty ratios print `N/A`, or `null` in JSON.

Baseline, reproducible with `--days 29 --until 2026-09-29T00:00:00Z` (UTC, all issue states, retrieved 2026-09-29): 212 issues created 2026-08-31 through 2026-09-28. All 212 are `unknown` because no `source:*` label existed yet on that history. 87 (41.0%) match the machinery heuristic and 16 bursts cover 79 issues. Reconciled against the GitHub search API `created:2026-08-31..2026-09-28` count of 212. The earlier epic figure of 405 issues created in 30 days (2026-09-10 snapshot, about 9 in 10 machinery by title) is a historical claim. It used a different title rule and window, so it is not comparable to this run. The weekly cost-governance review cites this script's output.

## Detection Patterns

### Agent Detection

The utility detects agents in commit messages using these patterns:

- Direct agent names: `orchestrator`, `analyst`, `architect`, etc.
- Review attribution: `Reviewed by: security`
- Agent tags: `agent: implementer` or `[security-agent]`

### Infrastructure Files

Infrastructure commits are identified by these patterns:

- `.github/workflows/*.{yml,yaml}`
- `.github/actions/**`
- Root `lefthook` and `.lefthook` configs, with optional `-local` suffix
- `.config/lefthook` configs, with optional `-local` suffix
- Lefthook config extensions: `.yml`, `.yaml`, `.json`, `.jsonc`, `.toml`
- `build/**`, `scripts/**`
- `Dockerfile*`
- `docker-compose*`
- `*.tf`, `*.tfvars`
- `.env*`
- `.agents/**`

### Commit Types

Conventional commit prefixes are classified:

- `feat:` - Feature
- `fix:` - Bug fix
- `docs:` - Documentation
- `ci:` - CI/CD
- `refactor:` - Refactoring

## Output Formats

### Summary (Default)

Human-readable console output with key metrics highlighted.

### Markdown

Formatted markdown suitable for dashboards and reports. Can be saved directly to `.project-toolkit/metrics/` for archival.

### JSON

Structured data for programmatic consumption and CI integration.

## CI Integration

See `.github/workflows/agent-metrics.yml` for automated weekly metrics collection.

The workflow:

1. Runs weekly on Sundays
2. Collects metrics for the previous 7 days
3. Generates a markdown report
4. Creates a PR with the report (if significant changes)

## Manual Report Generation

To generate a monthly dashboard report:

```bash
# Generate report
python .claude/skills/metrics/collect_metrics.py \
    --since 30 \
    --output markdown \
    > .project-toolkit/metrics/report-$(date +%Y-%m).md

# Review and commit
git add .project-toolkit/metrics/
git commit -m "docs(metrics): add monthly metrics report"
```

## Extending the Utility

### Adding New Metrics

1. Define the metric in `docs/agent-metrics.md`
2. Add collection logic to `collect_metrics.py`
3. Update the output formatters
4. Add tests if applicable

### Adding New Agent Patterns

Update the `AGENT_PATTERNS` list to detect new agent references.

### Adding Infrastructure Patterns

Update the `INFRASTRUCTURE_PATTERNS` list for new infrastructure file types.

## Troubleshooting

### No Agents Detected

- Ensure commit messages reference agents explicitly
- Check that conventional commit format is used
- Verify the patterns match your team's conventions

### Git Errors

- Confirm you're in a git repository
- Check that the repository has commits in the date range
- Verify git is available in PATH

## Related Documents

Backticked paths below are in the `rjmurillo/ai-agents` repository. They do not ship with this skill; a consumer install cannot resolve them.

- `docs/agent-metrics.md`. Agent metrics definitions.
- `.project-toolkit/metrics/dashboard-template.md`. Dashboard template.
- `.project-toolkit/metrics/baseline-report.md`. Baseline report.
- `.github/workflows/agent-metrics.yml`. CI workflow.

<!-- vendor-portability: declared. This skill reads the consumer's .agents/* artifacts as metric inputs and can archive formatted output to .project-toolkit/metrics/. Inputs are whatever the consumer repo contains; the archive path is an optional write target created on demand. It also cites docs/agent-metrics.md, .project-toolkit/metrics/dashboard-template.md, .project-toolkit/metrics/baseline-report.md, and .github/workflows/agent-metrics.yml as background reading. Issue #2050. -->
