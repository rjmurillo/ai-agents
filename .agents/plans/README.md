# Execution Plans

Execution plans are first-class versioned artifacts for complex, multi-step work.

## Directory Structure

| Directory | Purpose |
|-----------|---------|
| `active/` | Plans currently in progress |
| `completed/` | Successfully finished plans |
| `abandoned/` | Plans stopped with documented rationale |

Retired plans predating this lifecycle live in `.agents/archive/plans/`. See
that directory's `README.md` for the per-plan verdict and evidence.

A plan left in `active/` after its work ships misdirects agents at closed
milestones and deleted paths. Close a plan out when the work lands: the
`execution-plans` skill exposes `complete plan` and `abandon plan` for that.

## Creating a Plan

1. Copy `TEMPLATE.md` to `active/{slug}.md`
2. Fill in metadata, objectives, and related links
3. Update progress as work proceeds

## Related

- Skill: `.claude/skills/execution-plans/SKILL.md`
- Tech Debt Registry: `.agents/debt/tech-debt-registry.md`
- Source: [OpenAI Harness Engineering](https://openai.com/index/harness-engineering/)
