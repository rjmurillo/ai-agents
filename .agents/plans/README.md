# Execution Plans

Execution plans are first-class versioned artifacts for complex, multi-step work.

## Directory Structure

| Directory | Purpose |
|-----------|---------|
| `active/` | Plans currently in progress |
| `completed/` | Staging: where the `complete plan` trigger drops a finished plan |
| `abandoned/` | Staging: where the `abandon plan` trigger drops a stopped plan |

Both staging directories should be empty at rest. Retired plans move to
`.agents/archive/plans/`, which is where this repository
has put finished plans for its whole history. The archive README records the
2026-07-26 audit and the per-plan verdict behind each move.

A plan left in `active/` after its work ships misdirects agents at closed
milestones and deleted paths. Close a plan out when the work lands: the
`execution-plans` skill exposes `complete plan` and `abandon plan` for that.
Those triggers still write to `completed/` and `abandoned/`, which is the
drift that sent the 2026-07-26 batch on a round trip. Tracked in #3426.

## Creating a Plan

1. Copy `TEMPLATE.md` to `active/{slug}.md`
2. Fill in metadata, objectives, and related links
3. Update progress as work proceeds

## Related

- Skill: `.claude/skills/execution-plans/SKILL.md`
- Tech Debt Registry: `.agents/debt/tech-debt-registry.md`
- Source: [OpenAI Harness Engineering](https://openai.com/index/harness-engineering/)
