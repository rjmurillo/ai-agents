# Skill: Draft PRs to Avoid Bot Costs

## Skill Statement
Keep PRs as DRAFT until ready for review to avoid triggering expensive bot runs.

## Trigger Condition
- Creating a new PR
- Pushing to a PR branch

## Action Pattern (MUST)
1. Create PR as **DRAFT** (`gh pr create --draft`)
2. Batch all changes locally (multiple commits)
3. Push **once** when ready for review
4. Convert to ready-for-review only when seeking feedback

## Anti-Pattern (AVOID)
```text
❌ Commit → Push → Commit → Push → Commit → Push
   (Each push triggers: Copilot, CodeRabbit, Gemini, CI/CD)

✅ Commit → Commit → Commit → Push (once)
   (Single trigger of all bots)
```

## Quantified Impact
Each push to a non-draft PR triggers:
- GitHub Actions CI runs (~$0.01-0.10 per run)
- Copilot review (~context tokens)
- CodeRabbit review (~API calls)
- Gemini review (~API calls)

If 5 pushes instead of 1: **5x the cost**

## Evidence
- User feedback (2025-12-20 session)
- Observed behavior: Each PR push triggers multiple bot reviews

## Atomicity Score
98% - Single, actionable behavior

## Tags
cost-efficiency, github, pr-workflow, bot-management
