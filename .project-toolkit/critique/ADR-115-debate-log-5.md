# ADR Debate Log: ADR-115 Hermes Pack Budget Source

## Summary

- **ADR**: `.project-toolkit/architecture/ADR-115-native-plugin-support-per-host.md`
- **Prior debate log**: `.project-toolkit/critique/ADR-115-debate-log-4.md`
- **Trigger**: owner decision, Richard, 2026-11-15, in PR #7387. The skillforge judging code moves into a new shipped module, `_conformance_judging.py`. The `project-toolkit-knowledge` pack was at 380 of its 380-file budget, so `packMaxFiles` rose to 381.
- **Panel**: reduced (architect and critic). The edit touches Decision 6 prose only; the build check in `build/scripts/hermes_pack_checks.py` is unchanged.

## Pre-review evidence

- Measured on 2026-11-15 at `bd8245969`: `src/hermes/project-toolkit-knowledge` holds 381 files, 51 of them under `lib/`. `src/hermes/project-toolkit-delivery` holds 344.
- `build/scripts/hermes_pack_config.py` refuses a `packMaxFiles` value above 400.

## Round 1

### Architect

Vote: Disagree-and-Commit.

- P1: the ADR said `lib/` holds 40 files and the skill budget is 340. The measured `lib/` count is 51, so the figures no longer fit.
- P1: no stated trigger for when a budget raise should become a pack split.
- P2: the edit carried a date one day ahead of the session date.

### Critic

Vote: Disagree-and-Commit.

- P1: the skill budget figure is stale.
- P1: the date is wrong.
- P1: a literal budget in the ADR makes every future bump an ADR edit with a debate log.
- P2: "one file at a time" is review policy, not a build check.

### Changes made after round 1

- Decision 6 no longer states the budget, the `lib/` count, or the skill budget. It names `packMaxFiles` in `templates/platforms/hermes.yaml` as the one source.
- Decision 6 says the build refuses a value above 400, and that raising the budget is a review decision: a pull request that needs room raises it by what it adds, or moves a skill to a pack with room.
- The build-fails list says "exceeds `packMaxFiles`" with no number.
- No split threshold such as 395 was added. The owner has not set one.

## Round 2

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept. No P0 or P1. P2: "raises it by what it adds" is loose but acceptable. |
| critic | Accept. No P0 or P1. P2: the same wording is looser than round 1's text and acceptable. |

## Owner checkpoint

A later `/review` pass on PR #7387 noted that round 1's architect P1 (no split trigger) was closed without a recorded decision. The owner, Richard, chose on 2026-11-15 to record it as an accepted risk. Decision 6 now says repeated raises can reach 400, the next file then fails the build, and the owner decides whether to split the pack. No earlier trigger is set. This records an owner decision and changes no other text, so no further panel round ran.

## Outcome

Outcome: Consensus in round 2, both reviewers Accept. Decision 6 points to `packMaxFiles` in `hermes.yaml` instead of restating it, so a later budget change needs no ADR edit. The ADR stays `proposed`.
