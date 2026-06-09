# Issue Triage Sweep 2026-06-06 (session 2372)

Autonomous sweep of all 32 open issues (workflow-orchestrated). Full disposition
matrix: `.agents/analysis/2026-06-06-issue-triage-sweep.md`.

## Final outcome (USER-RATIFIED 2026-06-06)

rjmurillo explicitly chose "Accept dispositions" when asked how to handle the
remaining open issues. The dispositions below are the agreed end state; do NOT
re-open this as unfinished work in a later session.

- Closed 3: #2471 (done by PR #2337), #907 (superseded by agent->skill refactor),
  #1351 (Renovate dashboard, owner said bot-managed).
- Fixed via PR: #2481 (verify_issue_close citation-truth gate + epic guard);
  #2483 (#2443 ScriptCommit provenance); #2485 (#139 dorny output rename, 16
  workflows + convention doc); #2487 (#2477 duplicate-PR preflight scripts).
  Docs PR #2484. Each baselines the pre-existing #2337 extract_evidence.py vendor
  offender (#2050 debt).
- 25 kept-open and RATIFIED as correct: blocked on non-existent deps
  (#1073-1077 awesome-ai repo + 1700-file migration), human governance/consensus
  (#702 ADR approval), product/architecture decisions that are the maintainer's
  (#134, #1574, #1774, #1875, #2014, #2388), sequential analysis phases
  (#2478->#2479->#2480), epics with open children (#1944, #1948-1950, #1949),
  and large migrations (#2050). Fresh comments left on #134, #702.

## Reusable learnings

- **"Fix all" has a governance ceiling.** Issues that need an ADR approval, a
  product/architecture decision, or a non-existent dependency are NOT
  autonomously fixable; the repo's own rules (governance.md human-approval,
  voice.md Confusion Protocol, builder-ethos boil-lakes-flag-oceans) forbid
  forcing them. When a "fix everything" directive collides with these, surface
  the conflict via AskUserQuestion rather than manufacturing low-value PRs.
- **Honor same-day maintainer dispositions (User Sovereignty).** sonnet triage
  recommended CLOSE on #1984/#1997 which the maintainer had kept open hours
  earlier; reconcile verdicts against the latest maintainer comment before acting.
- **Workflow burst rate-limit.** 32 parallel subagents at once = total throttle
  failure; sequential waves of 4 + a retry pass works. See
  [[workflow-rate-limit-and-worktree-leak]].
- **#2337 shipped an unbaselined vendor-portability offender** (extract_evidence.py
  hard-codes .agents/), silently failing the gate for every later skill-.py PR.
- **Serial plugin.json bumps collide.** Sequential PRs each bumping plugin.json
  (0.5.151, 0.5.152) conflict on merge; stagger versions and expect trivial
  conflict resolution. See [[pr-autofix-stale-main-and-serialization]].
- **gh act can't evaluate dynamic `${{ fromJson() }}` matrices** (pre-existing in
  ai-session-protocol.yml); the pre-push offers SKIP_WORKFLOW_LOCAL_TEST for it,
  used after confirming actionlint passes and the matrix is pre-existing.
