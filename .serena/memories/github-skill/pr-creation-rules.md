# PR Creation Rules

**Last Updated**: 2026-07-21
**Sessions Analyzed**: 1

## Constraints (HIGH confidence)

- Use `new_pr.py` for PR creation, not raw `gh pr create`. The skill-first rule
  remains a MUST in `AGENTS.md`; PR #3293 retired its runtime blocking hook.
  (Session 2, 2026-04-10; retirement 2026-07-21)
  - Historical evidence: the retired hook blocked `gh pr create` and redirected
    to `.claude/skills/github/scripts/pr/new_pr.py`.
  - Script: `python3 .claude/skills/github/scripts/pr/new_pr.py --title "..." --body "..."`