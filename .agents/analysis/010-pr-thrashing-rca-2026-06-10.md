# PR Thrashing and Churn RCA (2026-06-10, session 2382)

> Goal: identify why PR submissions do not pass checks on the first run, root-cause the
> load-bearing failures, file issues, and ship fixes. Sample window: the 50 most recent
> merged PRs (#2397 to #2529), the 11 open PRs at capture time, and the live CI behavior
> of the two fix PRs this session opened (a natural experiment on the gates themselves).

## 1. Headline findings

| # | Finding | Evidence | Tracking |
|---|---------|----------|----------|
| 1 | Renovate-owned literals duplicated in tests turn every action bump into a red main; red main then blocks the first CI run of every `.py` PR | `tests/workflows/test_post_pr_retrospective.py` asserted an exact action SHA; bumps #2486, #2506, #2516 each re-broke it; open PRs #2532/#2535 had to stack on the fix branch to get green CI | #2348 (reopened), fix in flight: #2530 |
| 2 | Two dependency bots (Dependabot + Renovate) owned the same ecosystems: duplicate bump PRs, incompatible pin-comment formats, and one pin left permanently unmanaged | #2505 (Dependabot) vs #2506 (Renovate) same dep, same day; Dependabot rewrote `claude.yml` without the `# vX.Y.Z` comment Renovate keys on, so #2516 skipped it and it froze at v1.0.141 | **#2542 (new)**, fixed in PR #2544 |
| 3 | The shared `plugin.json` version counter makes every pair of concurrent plugin-source PRs collide; the resolver had no rule, and accept-main would re-trip the gate | Open PRs #2532 and #2535 both bumped 0.5.167 to 0.5.168 while main had already taken 0.5.168; whichever lands second re-bumps and re-runs everything | **#2543 (new)**, mitigated in PR #2547 |
| 4 | Claude web containers cannot pass the full pre-push suite: host signing config 400s on tmp-repo fixture commits (57 tests), root makes chmod tests no-ops (5 tests), `gh act` is absent for workflow-local tests | Hit live while shipping #2547 and #2544 this session | **#2548 (new)**; root-skip guards shipped in #2547 |
| 5 | AI quality gate emits mostly low-confidence noise; first-pass signal ratio is 24%, dominated by `CONTEXT_MODE: summary` disclaimers | Phase 1 baseline (`009-phase1-agent-comment-baseline.md`): 42 signal vs 131 noise across 120 agent runs; reconfirmed live on PR #2544 where 9 of 10 agents WARNed purely on summary-context grounds | #2478 (done), #2479 (done), #2480 (Phase 3 pending) |

## 2. Quantified churn signals

- **Meta-fix tax.** Of the 50 most recent merged PRs, roughly 25 are fixes to the automation
  itself (pre-commit/pre-push gates, pr-autofix, github-skill scripts, validators, hooks, CI
  workflows), about 10 are dependency bumps, and only a minority deliver new capability.
  The pipeline currently spends most of its PR throughput repairing the pipeline.
- **CI fan-out.** A single PR push triggers about 30 workflow runs (measured directly:
  two consecutive pushes produced 60 runs on 2026-06-10). Every avoidable re-push
  (rebase after a version-counter collision, fix-commit after a gate false positive)
  costs the full fan-out plus the 10-agent AI quality gate.
- **Live first-run failure experiment.** This session's own PR #2544 failed its first
  `Validate PR` run because the description validator counts reference-only path mentions
  (including `path:line` citations) as change claims unless they sit inside fenced blocks
  or admonitions. The PR body had to be rewritten to validator conventions. The same
  validator class was recently patched for `Refs #N` linkage (#2502): this gate is a
  recurring first-run failure source for well-formed PRs.

## 3. Root-cause chains

### 3.1 Red main cascade (finding 1)

Renovate bumps a workflow action SHA. The test that hard-codes the same SHA is not run on
the Renovate PR (path filters: workflow-only change does not trigger Python tests), so the
PR automerges green. The next push to main runs the full suite: red. Every subsequent PR
that touches `.py` files inherits the failure on first run, and authors start stacking PRs
on the fix branch (#2532, #2535, #2547), which adds retarget churn after the base merges.
Root cause: a Renovate-owned value duplicated into a test (single source of truth
violation), with the path-filter bypass (`ci-infrastructure-006`) as the enabling layer.
Durable fix shape: assert pin SHAPE, not the literal (#2530).

### 3.2 Dual dependency bots (finding 2, #2542)

No single owner for dependency updates. Renovate was added with automerge; the older
Dependabot config was never retired. Beyond duplicate PR cost, the two bots' pin styles
are incompatible: Dependabot does not write the `@sha # vX.Y.Z` comment Renovate keys on,
so a Dependabot-touched pin exits Renovate management silently. That is how
`claude.yml:119` froze at v1.0.141 with no bot ever updating it again, while sibling
workflows moved to v1.0.142. Fix (PR #2544): delete `.github/dependabot.yml` (Renovate
`config:recommended` covers github-actions + pip; Dependabot security updates are
repo-settings driven and unaffected) and restore the commented pin.

### 3.3 Plugin version counter collision (finding 3, #2543)

The version-bump gate requires head > merge-base whenever plugin source changes, so all
concurrent plugin PRs bump to the same next number. Same-number bumps merge silently and
then fail the gate (`not-bumped`) after the first PR lands; different-number bumps
conflict textually. Either way the second PR pays a full thrash round. The merge-resolver
had no rule for the manifest, and its only strategy (accept main) would recreate the
`not-bumped` state. Mitigation (PR #2547): version-only plugin.json conflicts resolve to
one patch bump above the higher side. The structural fix (auto-bump on main, removing the
contention) is recorded in #2543 and needs an ADR-level decision.

### 3.4 Container/CI environment mismatch (finding 4, #2548)

Three independent mismatches between the Claude web container and CI runners mean the
pre-push full suite cannot pass locally exactly when it matters (any `.py` change):
host gpgsign + signing server that 400s outside the project repo (57 git-fixture tests),
root user neutralizing chmod-based permission tests (5 tests, fixed via `skipif` in
#2547), and `gh act` absent for the workflow-local-test phase (`SKIP_WORKFLOW_LOCAL_TEST`
required on every workflow PR). Each costs a failed push plus archaeology per session and
pressures agents toward hook bypasses.

## 4. Process observations (documented, not separately filed)

- **Session-protocol gate forces shared-file coupling.** The pre-commit gate requires the
  session log staged (with sessionEnd MUSTs complete) on every commit, so one session's
  log file rides along in every PR it opens; concurrent PRs from one session then share a
  file that diverges per branch. Related metadata gaps already tracked in #2537 and #2531.
- **Generated-mirror lint wall.** Regenerating one copilot mirror surfaces ~1200
  pre-existing ruff violations; the pyproject exemption was duplicated into two in-flight
  PRs (#2532, #2535), guaranteeing a conflict between them. Whichever lands second should
  drop its copy.
- **Description-match validator strictness** (see section 2): treats `path:line` citations
  and reference mentions as change claims; PR authors must know the fenced-block and
  admonition conventions to pass first-run.
- **One run of PR #2544 mid-session shows the quality-gate noise live**: first run, 9 of
  10 agents WARN with summary-context disclaimers; after a repair push, several flipped to
  PASS having verified files directly. Phase 3 (#2480) remains the tracked fix.

## 5. What shipped from this session

| Item | Artifact |
|------|----------|
| Issue: single dependency bot | #2542 |
| Fix PR: remove dependabot.yml, repair claude.yml pin | #2544 (draft) |
| Issue: plugin.json version collision | #2543 |
| Fix PR: merge-resolver plugin-manifest rule + root-container test guards | #2547 (draft, stacked on #2530) |
| Issue: web-container pre-push environment gaps | #2548 |
| This analysis + Serena memory `analysis/pr-thrashing-rca-2026-06-10` | this PR |

## 6. Recommended next moves (priority order)

1. Merge #2530 (un-reds main; unblocks first-run CI for every `.py` PR), then retarget and
   land the stacked PRs.
2. Merge #2544 (stops duplicate bot PRs and pin drift at the source).
3. Land #2547, then decide #2543's structural option (auto-bump on main) via ADR.
4. Execute Phase 3 (#2480) prompt fixes for roadmap/analyst/devops, including full-diff
   context for the gate (the `CONTEXT_MODE: summary` disclaimers dominate the noise).
5. Implement #2548's conftest-level signing guard and the `gh act` provisioning-or-warn
   decision so web containers can push `.py` changes one-shot.
