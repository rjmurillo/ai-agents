# ADR Debate Log: ADR-102 ci-scripts MUST 9 quote correction

## Summary

- **ADR**: ADR-102 (`.project-toolkit/architecture/ADR-102-session-qa-binding-field-precedence.md`)
- **Rounds**: 1 of 10
- **Outcome**: Consensus, 2 of 2 Accept
- **Final Status**: unchanged (the edit changes no status or decision)
- **Panel**: reduced panel, architect and critic. The edit fixes one quoted phrase. It
  changes no enforcement logic and no rule that another gate reads.
- **Prior debate logs**: `ADR-102-debate-log.md`, closed. This log does not reopen it.

## Change

ADR-102 line 70 quotes MUST 9 of the former `ci-scripts` rule. The quote read "MUST come
from a named ref". The rule says "MUST be computed from a named ref". The edit replaces the
three wrong words. The citation path `.claude/rules/ci-scripts.md` stays as is. Open PR #7569
re-anchors that path in a separate change.

## Evidence

- `git show 655ff2f83c^:.claude/rules/ci-scripts.md`, line 37: "MUST be computed from a named ref".
- Successor text, `.claude/skills/ai-agents-validation-and-qa/references/rule-ci-scripts.md`
  line 26: same wording.
- `git show 6977b40f11:.claude/rules/ci-scripts.md` (2026-08-21, the commit that wrote
  ADR-102): same wording. The old quote was wrong from the start. This edit does not rewrite
  history.

## Round 1 Summary

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept. One line changes in one file. No decision, status, frontmatter, or enforcement moves. Quote matches apart from the source's italics on "contains". |
| critic | Accept. No P0 or P1. The rule never said "come from", so this fixes a misquote. |

### P2 Findings (documented, non-blocking)

- The quote drops the source's `*contains*` emphasis. Both seats rated this cosmetic.
- `.project-toolkit/critique/ADR-102-debate-log.md` line 169 repeats the old misquote. It is
  a closed historical record, so it stays unchanged.
- The `.claude/rules/ci-scripts.md` path is stale on main. PR #7569 owns that fix.

## Verdict

Accepted by both seats in round 1. No dissent to record.
