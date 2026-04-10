# Stale Comment Detection on Multi-Commit PRs

## Pattern
Bot reviewers (Gemini, Copilot) review each commit independently. When commit N+1 deletes or replaces files from commit N, comments on those files become stale noise.

## Evidence
PR #1589: 8 of 10 bot review comments referenced files deleted in commit 2 (`3cb05ee9`). The bash `exit_code_handler.sh` was replaced by Python `run_with_retry.py`. All 8 stale comments were noise.

## Detection
Use `detect_stale_pr_comments.py` in `.claude/skills/github/scripts/pr/` to check if commented files exist at PR HEAD before triaging.

```
python3 .claude/skills/github/scripts/pr/detect_stale_pr_comments.py --pull-request N
```

## Action
Before triaging bot review comments on multi-commit PRs, run stale detection first. Stale comments can be resolved with a single reply noting the file was superseded in a later commit.