# New Script Placement Rules

**Last Updated**: 2026-04-10
**Sessions Analyzed**: 1

## Preferences (MED confidence)

- New PR utility scripts belong in the existing github skill suite (`.claude/skills/github/scripts/pr/`), not as standalone skills. Check existing capability before building new. (Session 2, 2026-04-10)
  - Evidence: User steered "should these be separate skills, or improvements to the existing github suite?" after 4 candidates were proposed as standalone skills
  - Decision: pr-stale-comment-detection placed as `detect_stale_pr_comments.py` in existing suite. 3 other candidates dropped (capability already existed or wrong ownership).