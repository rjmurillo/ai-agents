# The post merge version bot left main inconsistent without raising a red check

**Atomicity**: 90%
**Category**: Release automation
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E111. State checked on main at 1be533c496 (2026-11-26).

## Question

Can a post merge bot keep plugin versions in sync on a protected branch?

## Conventional answer

ADR-091 assigned plugin version bumps to a post merge bot to keep main consistent.

## First-principles position

Within hours of PR 4147 merging, the bot design left manifest versions out of sync. The squash message suppressed the trigger. The ruleset barred bot writes, and the bot-owned version flag blocked manual repair. A workflow that never starts cannot raise a failing check.

## Evidence with limits

- `[skip ci]` in the squash body suppressed `post-merge-version-bump.yml`, which had 0 runs (2026-08-01).
- A query of ruleset 11104075 listed `RepositoryRole` id 5 as the sole bypass actor (2026-08-01). The actions bot did not have bypass rights.
- The `bot_managed` flag blocked manual repair (2026-08-01).
- Main had inconsistent manifest versions at 0.6.5493 (2026-08-01).
- Limits: One repository and one ruleset. The ruleset query is direct evidence. The run count and squash-message cause come from the ADR and PR accounts.
- State on main at 1be533c496 (2026-11-26): fixed. ADR-092 superseded ADR-091 by omitting the manifest version. ADR-092:138 records the skip marker and ADR-092:142 records the bypass rule.

## Decision

Before relying on a post merge bot, test the trigger on a squash commit. Verify the bot can write under the branch rules. A bot that never runs raises no red check.
