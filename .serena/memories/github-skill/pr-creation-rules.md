# PR Creation Rules

**Last Updated**: 2026-04-10
**Sessions Analyzed**: 1

## Constraints (HIGH confidence)

- Use new_pr.py for PR creation, not raw gh commands. The skill-first hook blocks gh pr create. (Session 2, 2026-04-10)
  - Evidence: `gh pr create` blocked by PreToolUse hook invoke_skill_first_guard.py with message "Blocked: Raw gh command detected. Use skill at .claude/skills/github/scripts/pr/new_pr.py"
  - Script: `python3 .claude/skills/github/scripts/pr/new_pr.py --title "..." --body "..."`