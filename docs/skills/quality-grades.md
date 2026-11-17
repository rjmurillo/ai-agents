# quality-grades

Grades each product domain in your repository from A to F across six architectural layers. You get a markdown or JSON report with gaps, file counts, and trends over time.

## When to use it

- You start a quality improvement effort across several domains.
- You need a repo health report for stakeholders.
- You want to know which domains need the most attention.
- You want to track quality trends by running the grader repeatedly.
- You say `grade quality`, `audit domain quality`, `show quality gaps`, `run quality grades`, or `domain quality report`.

## When not to use it

- Maintainability scoring of one file or module: use [`code-qualities-assessment`](code-qualities-assessment.md) instead.
- A pre-merge review of a change: use [`review`](review.md) instead.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:quality-grades`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the quality-grades skill to grade every domain in this repo and write the report to quality-grades.md.
```

The skill runs `grade_domains.py` from the repository root. At the end you see a report with a grade per domain and layer, plus a list of gaps ranked by severity.

## What you get

Each domain gets a grade for six layers: agents, skills, scripts, tests, docs, and workflows.

| Grade | Score | Meaning |
| --- | --- | --- |
| A | 90-100 | Full coverage, no known gaps |
| B | 75-89 | Minor gaps, non-blocking |
| C | 60-74 | Gaps present, should address |
| D | 40-59 | Blocking quality gaps |
| F | 0-39 | Broken or missing |

Gaps carry one of three severity labels: `critical` (missing required artifact), a middle label for important gaps to address soon, and `minor` (nice to have).

When you write the report with `--output`, the script loads the earlier JSON results and labels each domain's trend:

| Trend | Meaning |
| --- | --- |
| `improving` | Score rose 5 or more points |
| `stable` | Score changed less than 5 points |
| `degrading` | Score fell 5 or more points |
| `new` | No earlier data |

## Advanced use

Run the scripts directly from the root of a checkout of this repository:

```bash
uv run python .claude/skills/quality-grades/scripts/grade_domains.py --help
uv run python .claude/skills/quality-grades/scripts/check_grade_changes.py --help
```

`grade_domains.py` flags:

| Flag | Effect |
| --- | --- |
| `--repo-root` | Repository root (default: current directory). |
| `--domains` | Grade only the named domains instead of auto-detecting. |
| `--format` | `markdown` (default) or `json`. |
| `--output` | Write the report to a file instead of stdout. |
| `--top-n` | Show only the top N domains by gap count. |

Exit codes for `grade_domains.py`: `0` means the report was generated. `2` means `--repo-root` has no `.claude` directory or no domains were detected, so the report is not valid.

```bash
uv run python .claude/skills/quality-grades/scripts/grade_domains.py --domains security memory --format json --output grades.json
```

`check_grade_changes.py` reads a JSON grades file from `grade_domains.py`, flags domains whose score falls below a threshold, and opens a GitHub issue when a domain's trend is degrading or its score falls below the threshold. Flags: `--grades-file` (required) and `--threshold` (default 60). Exit `0` means no degradation. Exit `1` means a script error or degradation was detected.

> [!WARNING]
> `check_grade_changes.py` runs `gh issue create` against the repository that `gh` resolves from your current directory. It has no dry-run mode. Run it only in the repository where you want the issue filed.

```bash
uv run python .claude/skills/quality-grades/scripts/check_grade_changes.py --grades-file grades.json
```

Run the grader from the repository root so layout detection works. The docs layer scans `docs/`, `.agents/`, and `.project-toolkit/`. If your repository has no `.agents/` directory, the docs layer is graded on whatever documentation exists instead of failing. Address `critical` gaps first, then rerun to track movement.

The [`quality-auditor`](../agents/quality-auditor.md) agent covers the same repo-wide A to F grading as an agent.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`code-qualities-assessment`](code-qualities-assessment.md): file-level maintainability scoring.
- [`review`](review.md): pre-merge review.
- [`quality-auditor`](../agents/quality-auditor.md): the agent form of repo-wide grading and trend tracking.
- Source: [`SKILL.md`](../../src/claude/skills/quality-grades/SKILL.md)
- Reference: [`solid-principles.md`](../../src/claude/skills/quality-grades/references/solid-principles.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
