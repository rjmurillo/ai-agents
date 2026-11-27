# skill-doctor

Scores how your installed skills performed in recent local agent sessions, then drafts evidence-backed edits. You get one self-contained HTML report with a grade, three top findings, and candidate skill changes with handoff prompts. It can also check a repository for ADR drift: duplicate numbers, broken links, stale records, and decisions in git history that no ADR names.

## When to use it

- You want to grade your agent setup from real conversations.
- A skill did not fire when it should have, or keeps failing.
- You want to know whether a repository's ADRs match its git history.
- Trigger phrases: `diagnose skill usage`, `grade my agent setup`, `run skill-doctor`, `check ADR drift`.

## When not to use it

- You want to create a skill: use [`skill-bootstrap`](skill-bootstrap.md) for a library, or [`skillforge`](skillforge.md) for one skill.
- You want to tune a skill against an eval: use [`skillopt`](skillopt.md) instead.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:skill-doctor
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/skill-doctor`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /skill-doctor skill to ...`.

The skill asks two questions. First, which conversations to grade: this repository, all conversations, or chosen projects. Second, which skills to evaluate: project and global skills, or project skills only. It then collects, scores, and renders the report. Collection and rendering run locally.

For `check ADR drift` alone, the skill skips both questions, confirms the repository, scans it, and renders an ADR drift report with no scorecard.

## What you get

- `report.html` in a fresh temp directory, with the scorecard, findings, and suggested skill edits. A Share button saves a PNG locally. The skill ends by printing the absolute path.
- A grade across efficiency, code quality, procedure compliance, verbosity, and skill coverage, plus an overall score.
- Candidate edits, each with status `unevaluated`, a unified diff, and handoff prompts for [`skillopt`](skillopt.md) or [`skillforge`](skillforge.md).
- With `--export-corpus`, a JSONL file of every collected user and assistant message, redacted and untruncated, for [`panning-for-gold`](panning-for-gold.md).
- A spoken summary of the grade and three findings, plus the renderer's `evaluation:` line.
- For ADR drift, an `ADR drift` section: findings by group (Setup, Numbering, Links, History) with a suggested fix each. History findings are candidates, not verdicts. Truncated history and unreadable paths are shown. The section never changes the grade.

Overall weights: efficiency 0.25, code quality 0.25, procedure compliance 0.20, verbosity 0.15, skill coverage 0.15. The skill notes that coverage rewards skill adoption and does not prove skills improved outcomes.

## Advanced use

The skill never edits your installed skill files and never starts skillopt or skillforge. Proposed files go under the report directory only. It keeps every candidate `unevaluated`, because static diagnosis cannot measure whether a change helps.

From the root of a checkout of this repository, every script accepts `--help`:

```bash
uv run python .claude/skills/skill-doctor/scripts/collect_sessions.py --help
uv run python .claude/skills/skill-doctor/scripts/audit_scores.py --help
uv run python .claude/skills/skill-doctor/scripts/render_report.py --help
```

| Script | Purpose |
| --- | --- |
| `collect_sessions.py` | Collect journals into `inventory.json` and bounded transcripts; `--export-corpus` also writes full-text JSONL |
| `audit_scores.py` | Validate `scores.json` and compute aggregates |
| `assemble_report.py` | Fill the `report.json` numbers and audit sections |
| `render_report.py` | Render `report.json` into `report.html`; `--open` requests a browser |
| `audit_manifest.py`, `audit_batches.py` | Validate manifests; assign and import review batches |
| `public_export.py` | Write an aggregate-only summary that is safe to share |
| `adr_drift.py` | `locate` ADR folders, `scan` a repository into a JSON file |

Collector scope flags: `--repo PATH` (repeatable), `--all-conversations`, `--include-global-skills`, `--harness auto|all|claude|codex|copilot|warp|pi|grok|zcode|hermes|droid|muse|t3|gemini`, `--days`, `--max-sessions`, `--min-idle-minutes` (default 15; sessions newer than that are skipped), `--no-include-subagents`, `--export-corpus PATH`, and `--out`. Subagent sessions are collected by default and graded apart from top-level sessions; `--no-include-subagents` drops them. Copilot folds its inline child events only when you pass `--include-subagents`. Exit `0` is success, `1` is invalid input or an unsupported claim, and `2` is bad arguments or an unreadable file.

`adr_drift.py` never writes into the scanned repository; `scan` writes only its `--out` file, which must sit outside it, and writes it whole or not at all. Exit codes: `0` ok, `2` bad arguments, unreadable input, a disallowed `--out`, a result over 5,000,000 bytes, or not a git repository, `3` a git command failed or timed out. `scan` reads 300 commits by default (`--max-commits`, `--since`) and reports `truncated` when it stopped early. The scan file also lists `read_errors` for files and folders it could not read, and `locate.rejected` for refused paths, each with its reason (for example, a folder outside the repository or an ADR file outside its folder). `report.json` names each scan file by path, and `render_report.py` reads it from the report folder (exit `2` on a missing, unreadable, or outside path). An ADR-only report needs `"mode": "adr_only"`. This skill checks ADR health only: finding decisions that no ADR records is skill-bootstrap's job.

Undocumented decisions come from [`skill-bootstrap`](skill-bootstrap.md): Step 1a runs its `bootstrap_adr.py scan` and shows the candidates in the report. Drafts go to the report folder only. Without skill-bootstrap installed, the report says that part is unavailable.

A conversation counts as failed when any applicable raw score is below 0.5. A failure caused only by a provider cutoff does not count. A passing conversation can support only a `Cut:` candidate, which removes a wasted instruction or step.

If the executing harness is unsupported, the skill stops before it reads any history. If no sessions are sampled, it reports that and does not invent scores. It also discloses sampling and partial collection.

`--export-corpus` is the feed for [`panning-for-gold`](panning-for-gold.md) session corpus mode. It writes whole, redacted messages and refuses a path inside the skill directory. The T3 and Gemini antigravity sources (`--t3-home`, `--gemini-home`) read only with this flag, never reach scoring, and export only with `--all-conversations` because they record no repository path. The file holds full conversation text, so keep it out of any repository.

When [`skill-bootstrap`](skill-bootstrap.md) invokes this skill, it reuses that run's scope, omits `--open`, and returns the report path.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`skill-bootstrap`](skill-bootstrap.md): invokes this skill to diagnose existing skills.
- [`skillopt`](skillopt.md): evaluates a candidate against a scored eval set.
- [`skillforge`](skillforge.md): routes `new-skill` candidates.
- Source: [`SKILL.md`](../../src/claude/skills/skill-doctor/SKILL.md)
- Audit workflow: [`audit-workflow.md`](../../src/claude/skills/skill-doctor/references/audit-workflow.md)
- ADR drift: [`adr-drift.md`](../../src/claude/skills/skill-doctor/references/adr-drift.md)
- Supported harnesses: [`supported-harnesses.md`](../../src/claude/skills/skill-doctor/references/supported-harnesses.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
