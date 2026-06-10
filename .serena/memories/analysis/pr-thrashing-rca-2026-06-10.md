# PR Thrashing/Churn RCA (session 2382, 2026-06-10)

**Statement**: The dominant causes of PRs failing checks on first run (anti "one-shot") in ai-agents are (1) red main from Renovate-owned literals duplicated in tests, (2) dual dependency bots doubling bump frequency, (3) the plugin.json shared version counter colliding across concurrent PRs, (4) AI quality gate noise (52% signal at best, 24% first-pass).

## Quantified signals

- ~25 of the last 50 merged PRs are fixes to the automation itself (hooks, gates, validators, pr-autofix, github-skill, CI). ~10 are dependency bumps. New capability is a minority of throughput.
- A single PR push triggers ~30 workflow runs (measured 2026-06-10: two pushes = 60 runs).
- Main was red 2026-06-09/10: `tests/workflows/test_post_pr_retrospective.py` asserts exact action SHA; Renovate bump #2516 broke it (3rd recurrence: #2486, #2506, #2516). Fix in flight: PR #2530 (asserts pin SHAPE, not SHA). Red main forces stacked PRs (#2532, #2535 stacked on #2530's branch).

## Root causes found this session (new issues filed)

- **#2542**: Dependabot AND Renovate both manage github-actions + pip. Duplicate bump PRs (#2505 vs #2506 same dep same day), Dependabot writes comment-less pins Renovate then cannot track -> claude.yml stuck at v1.0.141 unmanaged. Fix: delete dependabot.yml, restore `# vX.Y.Z` pin comment in claude.yml.
- **#2543**: plugin version-bump gate makes every pair of concurrent plugin-source PRs collide on plugin.json (both bump to same next version). merge-resolver has no rule for it and its accept-main strategy would re-trip the `not-bumped` gate. Fix: version-only conflicts resolve to patch-bump(max(ours,theirs)).

## Already tracked (do not duplicate)

- #2348/#2530 red-main pin test; #2478-#2480 quality-gate noise (Phase 1 baseline: `.agents/analysis/009-phase1-agent-comment-baseline.md`); #2531 retro skeleton litter; #2537 session metadata; #2539 pre-push mypy duplicate-module; #2519-#2527 latent sweep (session 2381).

## Process observations (analysis doc has details)

- Session-protocol pre-commit gate requires sessionEnd MUSTs complete in the staged log on EVERY commit -> agents fill "end" evidence mid-session repeatedly; session log shared across concurrent fix branches -> conflicts on .agents/sessions/* (auto-resolved accept-main, losing branch entries).
- Generated mirror regen (src/copilot-cli) surfaces ~1200 pre-existing ruff violations; the pyproject exemption was duplicated in two in-flight PRs (#2532, #2535) -> guaranteed conflict.
- Renovate bump PR #2518 sat with `infrastructure-failure` label and status `pending` with 0 checks reported.

## Artifacts

- Analysis doc: `.agents/analysis/010-pr-thrashing-rca-2026-06-10.md`
- Session log: `.agents/sessions/2026-06-10-session-2382-analyze-recent-prs-thrashingchurn-rca.json`
