# pr-quality

Judges your working changes on six PR quality axes (security, QA, analyst, architect, DevOps, roadmap), or on one axis you name. It merges the verdicts into one answer about whether the branch is safe to push.

> [!NOTE]
> Each axis reads its criteria from the [`review`](review.md) skill's `references/<axis>.md`, so this gate and `/review` judge the same things. The JSON output schema is [`.agents/schemas/pr-quality-gate-output.schema.json`](../../.agents/schemas/pr-quality-gate-output.schema.json). The skill also cites [`.claude/lib/ai_review_common/verdict.py`](../../src/claude/lib/ai_review_common/verdict.py) for its merge rules. These files live in the `rjmurillo/ai-agents` repository. The skill is written for contributors to that repository.

## When to use it

- You want one pre-push verdict across all six axes.
- You want one axis only, such as a security pass on your diff: add `--axis security`.
- You say `/pr-quality`, `/pr-quality --axis security`, `run all the quality gates`, or `full pre-push review`.

## When not to use it

- You want the pre-merge gate: use [`review`](review.md) instead. This skill reads working changes, not the PR.
- You want an inline security review of a snippet: use [`security-review`](security-review.md) instead.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:pr-quality main
/project-toolkit:pr-quality --axis qa main
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/pr-quality`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /pr-quality skill to ...`.

`--axis` takes `security`, `qa`, `analyst`, `architect`, `devops`, or `roadmap`. The base branch defaults to `main`.

## What you get

For each axis, a block that starts with `AXIS:` and `VERDICT:`, then findings that cite `path:line`, then a JSON block that names the axis. With more than one axis, a summary table follows:

```text
| Agent | Verdict | Status | Key Findings |
|-------|---------|--------|--------------|
| Security | [verdict] | [emoji] | [summary] |
| ...      |           |         |           |

FINAL VERDICT: [PASS|WARN|UNKNOWN|CRITICAL_FAIL]
```

| Final verdict | What to do |
| --- | --- |
| `PASS` | Safe to commit and push. |
| `WARN` | Review the findings. Address them if time permits. Safe to push. |
| `UNKNOWN` | An axis did not evaluate. Find which one and re-run. Do not treat this as `PASS`. |
| `CRITICAL_FAIL` | Fix the blocking issues before you push. |

If the change set is empty, the skill prints `PASS` and stops. The count includes untracked files, so a branch of only new files is not empty.

## Advanced use

How a run works:

1. The skill accepts the base only when it matches `^[A-Za-z0-9._/-]+$` and does not start with `-` or `/`. It resolves the base to a commit, then takes the merge base with `HEAD`. Either command failing, or exiting nonzero, stops the run.
2. It counts changed files, tracked plus untracked, and takes the diff once.
3. For each selected axis, it reads that axis's criteria file and judges the same diff. Findings are additive: a failed axis does not stop the run.
4. With more than one axis, it merges the verdicts.

Merge rules (canonical source: `merge_verdicts` in [`.claude/lib/ai_review_common/verdict.py`](../../src/claude/lib/ai_review_common/verdict.py)):

| Tokens present | Final verdict |
| --- | --- |
| Any `CRITICAL_FAIL`, `REJECTED`, `FAIL`, `NEEDS_REVIEW`, or `NON_COMPLIANT` | `CRITICAL_FAIL` |
| Any `WARN` or `PARTIAL`, and no critical token | `WARN` |
| Any `UNKNOWN`, `DID_NOT_RUN`, or unrecognized token, and no critical or warn token | `UNKNOWN` |
| All `PASS` or `COMPLIANT` | `PASS` |
| No input | `UNKNOWN` |

[`pr-comment-responder`](pr-comment-responder.md) points local quality gates here before a push. `review` stays the pre-merge gate and writes the marker that [`ship`](ship.md) validates.

To add a seventh axis, add its criteria file to the `review` skill's references. Then, in `templates/skills/pr-quality.SKILL.md.tmpl`, add one row to the Axes table and one to the summary table, and run `uv run python build/scripts/build_all.py`.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`review`](review.md): the pre-merge gate, and the owner of the axis criteria.
- [`security-review`](security-review.md): inline security review of a diff or snippet.
- Source: [`SKILL.md`](../../src/claude/skills/pr-quality/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
