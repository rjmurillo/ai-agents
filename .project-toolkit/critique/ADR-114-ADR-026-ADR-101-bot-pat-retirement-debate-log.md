# ADR-026, ADR-114, ADR-101 Debate Log: BOT_PAT Retirement (2026-11-06)

## Context

Owner decisions of 2026-11-06 on issues #4607 and #5246:

- ADR-026 Decision 5 (BOT_PAT for attribution) is retired.
- ADR-114 Decision 11 item 5 is retired, with a dated amendment. Item 4 stays open.
- ADR-101 "Fork pull requests" records the fork attach question as deferred.

The companion code change removes every workflow read of `BOT_PAT`, deletes
`scripts/ci/check_bot_identity.py`, and makes
`tests/ci/test_workflow_secret_environment_scope.py` refuse `BOT_PAT`. That is
executable enforcement, so the full six-agent panel ran.

## Agent Positions (round 1)

| Agent | Verdict | Findings |
|---|---|---|
| architect | Accept | Text matches the diff. P2: name affected workflows, ADR-026 frontmatter, scrub lists. |
| critic | Disagree-and-Commit | P1: name the no-trigger effect on pushed commits. Stale git identity. P2: ADR-101 BOT_PAT paragraphs, date on ruleset claim. |
| independent-thinker | Disagree-and-Commit | ADR-026 implementation line reads as live. Narrow "no workflow" to workflow files. |
| security | Disagree-and-Commit | `process-prs` checkout persists the write token (pre-existing). Stale git identity. |
| analyst | Accept | All named claims verified in the tree. |
| high-level-advisor | Accept | Nothing is P0. Scrub-list mention is the one P1. |

## Resolutions

- ADR-026 implementation line labeled "(original, retired)".
- ADR-114 amendment names the pushes that no longer trigger workflows and the
  empty prior credential, and says the scrub lists keep the name on purpose.
- "No workflow file reads" replaces "No workflow reads".
- `pr-maintenance.yml` git identity changed to `github-actions[bot]`.
- ADR-101 deferral cites ruleset 11104075, read 2026-11-05. A retirement note
  follows the BOT_PAT paragraph.
- ADR-114 item 5 "Split it into..." marked as history.

## Round 2 (post-review edits)

The /review security and devops axes returned WARN. Edits made:

- ADR-114 amendment names the pushes `github.token` cannot make, who re-runs
  checks, the App token alternative not taken, and the new permission.
- ADR-026 "Rejected Alternative" line labeled original and retired.
- `artifact-insight-scanner.yml` scopes `GH_TOKEN` to the steps that call `gh`.
- The #7097 clause is removed from the ADR-101 note; nothing in the tree backs it.
- `apply_ai_conflict_resolution.py` already limits resolutions to conflicted
  files (`_require_conflicted`), so no new path filter is added.

- CI test `test_adr_hook_claims` read script names in the ADR-114 amendment as hook
  files. The amendment now says "four modules under `scripts/`" and gives a grep.

## Dissent

- security: `persist-credentials` on the `process-prs` checkout keeps the write
  token in `.git/config`. The token was `github.token` before this change too,
  so this is not a regression. Out of scope. Flagged for the owner.
- ADR-026 frontmatter keeps `status: accepted`. Decision 5 alone is retired, and
  the body says so.

## Outcome

Outcome: Consensus. Accept or Disagree-and-Commit from 6 of 6 seats after
round 1. The round 2 edits were not re-voted by the panel. Status of the ADRs: accepted, unchanged.
