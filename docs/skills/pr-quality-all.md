# pr-quality-all

Runs all six PR quality axes (security, QA, analyst, architect, DevOps, roadmap) against your working changes. It merges the six verdicts into one answer about whether the branch is safe to push.

> [!NOTE]
> The axes take their criteria from `.github/prompts/`. Their JSON output schema is `.agents/schemas/pr-quality-gate-output.schema.json`. The skill also cites `.claude/lib/ai_review_common/verdict.py` for its merge rules. These files live in the `rjmurillo/ai-agents` repository. The skill is written for contributors to that repository.

## When to use it

- You want one pre-push verdict across all six axes.
- You say `run all the quality gates`, `pr-quality all`, `full pre-push review`, or `run every review axis`.

## When not to use it

- You want one axis only: use [`pr-quality-security`](pr-quality-security.md), [`pr-quality-qa`](pr-quality-qa.md), [`pr-quality-analyst`](pr-quality-analyst.md), [`pr-quality-architect`](pr-quality-architect.md), [`pr-quality-devops`](pr-quality-devops.md), or [`pr-quality-roadmap`](pr-quality-roadmap.md) instead.
- You want the pre-merge gate: use [`review`](review.md) instead. This skill reads working changes, not the PR.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:pr-quality-all main
```

In GitHub Copilot CLI, or in a Claude Code session inside a checkout of this repository, drop the prefix: `/pr-quality-all`.

Pass the branch you merge into. With no argument, the skill uses `main`. It runs each axis on the same diff and prints one table and a final verdict.

## What you get

The skill prints this table first, with no text before it:

```text
| Agent | Verdict | Status | Key Findings |
|-------|---------|--------|--------------|
| Security | [verdict] | [emoji] | [summary] |
| QA | [verdict] | [emoji] | [summary] |
| Analyst | [verdict] | [emoji] | [summary] |
| Architect | [verdict] | [emoji] | [summary] |
| DevOps | [verdict] | [emoji] | [summary] |
| Roadmap | [verdict] | [emoji] | [summary] |

FINAL VERDICT: [PASS|WARN|UNKNOWN|CRITICAL_FAIL]
```

| Final verdict | What to do |
| --- | --- |
| `PASS` | Safe to commit and push. |
| `WARN` | Review the findings. Address them if time permits. Safe to push. |
| `UNKNOWN` | At least one axis crashed or returned no parseable verdict. Find which one and re-run. Do not treat this as `PASS`. |
| `CRITICAL_FAIL` | Fix the blocking issues before you push. |

If the change set is empty, the skill prints `PASS` and stops. The count includes untracked files, so a branch of only new files is not empty.

## Advanced use

How a run works:

1. The skill resolves the base from your argument, or `main` if you give none. It rejects an empty value or one that starts with `-`, then resolves it to a commit with `git rev-parse --verify --quiet`. A ref that does not resolve stops the run.
2. It counts changed files, tracked plus untracked.
3. It invokes each axis through the `Skill` tool and forwards the resolved SHA, not the branch name. All six axes judge the same diff.
4. It parses each axis's `VERDICT:` line. An axis with no parseable verdict is `UNKNOWN`, never `PASS`.
5. It merges the six tokens.

Merge rules (canonical source: `merge_verdicts` in `.claude/lib/ai_review_common/verdict.py`):

| Tokens present | Final verdict |
| --- | --- |
| Any `CRITICAL_FAIL`, `REJECTED`, `FAIL`, `NEEDS_REVIEW`, or `NON_COMPLIANT` | `CRITICAL_FAIL` |
| Any `WARN` or `PARTIAL`, and no critical token | `WARN` |
| Any `UNKNOWN`, and no critical or warn token | `UNKNOWN` |
| All `PASS` or `COMPLIANT` | `PASS` |
| No input | `UNKNOWN` |

`UNKNOWN` downgrades a would-be `PASS`, so a crashed axis cannot produce a green result. Real `WARN` and `CRITICAL_FAIL` findings override `UNKNOWN`. The skill runs all six axes even after one returns `CRITICAL_FAIL`, so you see the full list in one round.

Each axis also emits schema-bound JSON. A tool that consumes results should parse that JSON, not the table.

The skill is kept as a standalone surface by a recorded decision. [`pr-comment-responder`](pr-comment-responder.md) routes local quality gates here before a push. `review` stays the pre-merge gate and writes the marker that [`ship`](ship.md) validates.

To add a seventh axis, add its `pr-quality-<name>` skill, then add one row to the table and one line to step 3. The merge table does not change, because it works on tokens.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`pr-quality-security`](pr-quality-security.md): the security axis.
- [`pr-quality-qa`](pr-quality-qa.md): the QA axis.
- [`pr-quality-analyst`](pr-quality-analyst.md): the analyst axis.
- [`pr-quality-architect`](pr-quality-architect.md): the architect axis.
- [`pr-quality-devops`](pr-quality-devops.md): the DevOps axis.
- [`pr-quality-roadmap`](pr-quality-roadmap.md): the roadmap axis.
- [`review`](review.md): the pre-merge gate.
- Source: [`SKILL.md`](../../src/claude/skills/pr-quality-all/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
