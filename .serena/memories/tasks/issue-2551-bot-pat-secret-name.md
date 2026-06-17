# Issue 2551: dependabot/renovate auto-approve PAT secret name bug

## Question
Why did the "Auto-Approve and Auto-Merge Bot PRs" workflow fail with an empty GH_TOKEN on every renovate/dependabot PR, and what is the correct fix?

## Conventional answer (issue triage, 4 separate passes)
The workflow file is correct; `secrets.GH_ACTIONS_PR_WRITE` resolves empty because a repo admin never set or rotated the PAT. Verdict: NEEDS-HUMAN, no code change possible. Source: issue #2551 comments 2026-06-10 through 2026-06-17.

## First-principles position
The failure is a config-side bug, not a missing secret value. `GH_ACTIONS_PR_WRITE` is a bespoke secret name used in this ONE workflow and nowhere else in the repo (8 refs, all in `.github/workflows/dependabot-approve-and-auto-merge.yml`). The canonical repo write PAT is `BOT_PAT` (the `rjmurillo-bot` service account), referenced by 11 other workflows (46 refs) and MANDATED by ADR-026 Decision 5 for PR-automation attribution. The workflow (added in #2055, June 5) was the lone deviation from that policy. The bespoke secret was never provisioned, so it resolved empty. Repointing the workflow at `BOT_PAT` fixes it in code with an already-provisioned, ADR-compliant secret. No human gate.

## Evidence
- `grep -rhoE "secrets\.[A-Z_]+" .github/workflows/` -> BOT_PAT x46, GH_ACTIONS_PR_WRITE x8.
- ADR-026 Decision 5: "Use `BOT_PAT` secret instead of `github.token`... Change all `GH_TOKEN: ${{ github.token }}` to `GH_TOKEN: ${{ secrets.BOT_PAT }}`."
- `.github/workflows/dependabot-approve-and-auto-merge.yml` was the only file referencing GH_ACTIONS_PR_WRITE.

## Decision
Repointed all 8 secret refs to `secrets.BOT_PAT`; updated guard step names, error messages, rationale comments. Updated `tests/test_renovate_workflow_secret_guard.py` (PAT_SECRET = "BOT_PAT") and `tests/test_dependabot_workflow_token.py`. TDD: RED 9 failed -> GREEN 13 passed; mutate-confirm 3 failed on break, 13 passed on restore; actionlint exit 0. Branch fix/2551-bot-pat-secret-name. fetch-metadata stays on GITHUB_TOKEN (#2307).

## Reusable lesson
When a single workflow's secret "resolves empty," grep the secret name across all of `.github/`. If it appears in exactly one file while a sibling secret name dominates, suspect a wrong-name config bug before concluding the value is unset. Cross-check against ADR-026 (BOT_PAT is the canonical PR-automation PAT).
