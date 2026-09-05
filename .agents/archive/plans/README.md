# Archived Execution Plans

Plans retired from `.agents/plans/active/` on 2026-07-26. They were briefly
rehomed into `.agents/plans/completed/` and `.agents/plans/abandoned/` on
2026-07-27 and returned here on 2026-07-29; this directory is the terminal
destination. Every plan was
verified against two independent signals before it moved: its tracking issue
closed as completed, and the deliverable it names present on disk. Twelve of
the 13 are finished or superseded outright. The rest is residual work, tracked
in the follow-ups table at the bottom of this file, not left implicit in a
stale `In Progress` header. Nothing was deleted.

## Why these moved

`.agents/plans/active/` held 13 plans, all marked `Status: In Progress`, created
between 2026-04-11 and 2026-05-10. `completed/` and `abandoned/` were empty:
the lifecycle in `.agents/plans/README.md` had never been exercised. The work
itself had shipped months earlier, so the stale `In Progress` headers pointed
agents at closed milestones, renumbered specs, and deleted directories.

Two concrete confusion hazards this removes:

- `req-008-m1-skill-contracts.md` carries REQ-008 in its name, but REQ-008 is
  `review-axes-convergence`. The memory-first gate it documents became REQ-017.
- `review-axes-convergence.md` directs work at `.claude/review-axes/`, deleted
  in `c3ddc571` (PR #2043) when `/review` became a skill. The axes now live at
  `.claude/skills/review/references/`.

## Verification method

Issue closure alone was not treated as proof. Each plan needed both a closed
tracking issue and the named deliverable present in the working tree.

## Inventory

| Plan | Verdict | Evidence |
|---|---|---|
| `1574-stage1-claude-kit-vendor.md` | Complete | #1574, #1619, #1623 to #1632 all closed as completed. `packages/ai-agents-cli/` ships `@rjmurillo/ai-agents` 0.1.0. |
| `knowledge-integration.md` | Complete through the kill gate | M0 to M3 complete, gate verdict PROCEED. 54 `references/` directories and 206 reference files on disk. M4 scale-out continues under open issue #3421. |
| `PLAN-1854-agent-eval-harness-spike.md` | Complete | #1854 closed as completed. ADR-058 (agent eval discipline) landed. `evals/` holds the spike corpus and per-agent reports. |
| `PLAN-1884-pr-iteration-cost.md` | Complete, carrier changed | #1884 and #1885 closed as completed. Guards run from the `pre-push` job in `lefthook.yml` calling `scripts/validation/git_hook_policy.py`, not the planned `.claude/hooks/` PreToolUse shape. |
| `PLAN-1923-em-en-dash-enforcement.md` | Complete | Plan self-declares complete. #1923 closed, PR #1930 merged. `scripts/validation/checks_dash.py` plus the MUST NOT rule in `.claude/rules/universal.md`. |
| `PLAN-1926-spec-step0-first-principles-gate.md` | Complete | #1926 closed as completed. Step 0 gate present at `.claude/commands/spec.md:15`. |
| `PLAN-skill-catalog-triage-action-slate.md` | Complete | Epic #1944 and children #1946, #1949, #1950, #2925, #1932 all closed as completed. All five Tier 1 prune targets gone from `.claude/skills/`. REQ-007 and REQ-018 marked implemented. |
| `req-003-multi-tool-artifact-build.md` | Complete | All seven generators plus `build_all.py` present under `build/scripts/`. `.claude-plugin/marketplace.json` ships the two-plugin model. |
| `req-008-m1-skill-contracts.md` | Superseded, misnumbered | An M1 findings note, not a plan. Its REQ number was reassigned; the work it documents shipped as REQ-017. |
| `req-012-retro-fixes-pr-1965.md` | Complete | PR #1965 merged. M1 `wait_for_unresolved_zero.py`, M3 co-change checklist in `spec.md`, M4 `complete_session_log.py`, M5 `bot_cascade_advisory` in `git_hook_policy.py` all present. |
| `req-017-step-0-5-memory-first-gate.md` | Complete | All five milestones checked off in the plan. Step 0.5 gate present in `.claude/commands/spec.md`. |
| `review-axes-convergence.md` | Complete, then superseded | #1934 closed as completed by PR #1965. `.claude/review-axes/` later deleted in `c3ddc571` (PR #2043); the 6 axes became 12 under `.claude/skills/review/references/`. Stale references to the old path tracked in #3425. |
| `model-assignment-unification.md` | Abandoned, superseded | Abandoned 2026-09-03 after the research it depended on landed elsewhere. Successors: issue #5282 and ADR-052. Moved here from `.agents/plans/abandoned/` because the plans README requires both staging directories to be empty at rest (#3426). |
| `spec-005-command-skill-bundling-implementation.md` | Landed partial, registry now stale | `scripts/validation/bundle_registry.py` and `tests/test_command_bundles.py` exist, but all 15 registry rows fail and the check never left advisory mode. Tracked in #3424. |

## Reading these files

Treat the inventory as a historical audit. The plan files sit beside this
README with their original `Status: In Progress` headers intact, so the archive
matches what shipped; the real verdict for each is in the table above.

## Follow-ups filed

| Issue | Scope |
|---|---|
| #3424 | Command bundle registry is 15/15 stale and permanently advisory. |
| #3425 | Spec co-change example and canonical-source-mirror scope point at the deleted `.claude/review-axes/`. |
| #3426 | Nothing moves plans out of `active/`, so it refills with stale work. |

## Related

- `.agents/plans/README.md`. Lifecycle for live plans.
- `.claude/skills/execution-plans/SKILL.md`. The `complete plan` and
  `abandon plan` triggers that move a plan out of `active/`.
