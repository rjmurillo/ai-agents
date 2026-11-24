# ADR Debate Log: ADR-115 Hermes Authoring Pack

## Summary

- **ADR**: `.project-toolkit/architecture/ADR-115-native-plugin-support-per-host.md`
- **Prior debate log**: `.project-toolkit/critique/ADR-115-debate-log-5.md`
- **Trigger**: owner decision, Richard, 2026-11-24. Merging main into PR #7527 put the knowledge pack at 403 files, over the 400-file cap. The owner chose a new pack over excluding files (D1). The owner then chose to move the whole six-skill reference group (D2), because `skill-bootstrap` alone fails the cross-pack rule.
- **Panel**: full (architect, critic, independent-thinker, security, analyst, high-level-advisor). The change widens `FORCE_ALLOWED_PACKS`, a guard allowlist that the smoke enforces.
- **Result**: consensus in round 2. All six vote Accept.

## Pre-review evidence

All measured on 2026-11-24.

- `src/hermes/project-toolkit-knowledge` held 393 files on main at `2dbaabd7a8`. Merging main into PR #7527, which adds 10 files, counted 403.
- After the split: authoring 190, knowledge 256, delivery 398.
- `find_references` path edges: `skill-bootstrap` to `skillopt`, `skillopt` to `skillforge`, `skillforge` to `context-optimizer`, `skillify` to `skillforge`, `prose-self-check` to `skillforge`. No outside skill has a path edge into the six.
- Pinned `plugin_guard` (hermes-agent `63d0b94120`): authoring `caution` (49 low, 49 medium, 1 high), knowledge `safe`, delivery `caution`. Main's knowledge was `caution`, with the same high finding at `skillforge/references/script-design-rules.md:232`.
- `build_all.py --check` wrote 0 files.

## Round 1

### Architect

Vote: Accept.

- P1: no smoke run backs the new allowlist entry.
- P2: the `caution` on main implies a smoke failure the ADR did not state.
- P2: "the one time an old skill changed packs" is a prediction, not a rule.
- P2: the memory file said 393 where the ADR said 403.

### Critic

Vote: Disagree-and-Commit.

- P1: "no skill outside the six refers to any of them" holds only for path references. Seven skills name the six in prose.
- P1: the update path reinstalled only the knowledge pack.
- P1: no smoke run evidence.
- P1: this debate log did not exist.
- P2: the `lib/` count of 40 per pack is stale; it is 52.
- P2: troubleshooting named step 3 only.
- P2: main's smoke failure went unstated.

### Independent-thinker

Vote: Disagree-and-Commit.

- P1: the prose-reference gap, as the critic found.
- P1: "one time" is prose nothing enforces.
- P1: delivery at 398 fails on 3 more files, including shared `lib/` files.
- P2: delivery got no room.
- P2: the 393 and 403 counts disagree.

### Security

Vote: Accept.

- P1: the smoke checks the verdict only. A new high finding in authoring would still install.
- P2: the guide did not name the guard pin or say the high finding is reference prose.

### Analyst

Vote: Disagree-and-Commit.

- P1: the prose-reference gap.
- P1: the 403 count did not match the tree without its source.
- P2: missing debate log.
- P2: main's smoke failure went unstated.
- P2: the 255-file sentence may be stale.

### High-level-advisor

Vote: Accept.

- P1: missing debate log.
- P1: the 393 and 403 counts disagree.
- P2: state the split procedure as a rule.

### Changes made after round 1

- Decision 6 limits the reference claim to path references and lists the seven prose routes under Negative.
- Decision 6 states the rule: an old skill changes packs only by owner decision, recorded as a Decision 6 amendment, and takes its whole path-reference set. The `hermes.yaml` comment says the same.
- Decision 6 and the memory file give 393 on main at `2dbaabd7a8` and 403 after the merge.
- The smoke ran with `RUN_CLI_E2E=1` against hermes-agent `63d0b94120`. Main failed 7 of 7 at setup, because knowledge was `caution` and not allowlisted. This change passed 6 of 7.
- The one smoke failure is the guard negative control. Its `stuck-detection` fixture rates `safe` on main too, so the failure predates this change. Decision 6 records it.
- Negative states delivery's 2 files of room and the verdict-only allowlist gap.
- The `lib/` figure reads 52 per Hermes pack.
- The install guide names the guard pin and line 232, reinstalls all three packs on update, and names step 4 for authoring.
- A recount over packed skills found the largest reference group at 12 skills and 151 source files.

### Deferred

- Security P1, per-pack severity ceiling. Deferred. Delivery has had the same verdict-only gap since it joined the allowlist. A ceiling needs the guard snippet to report findings, which changes the smoke for both packs. The Negative section names the gap.

## Round 2

- Critic: Accept. All findings resolved once this log lands.
- Analyst: Accept. Remaining P2s were the 255-file sentence and the negative-control cause. Both are now measured and recorded.
- Independent-thinker: Accept. One P2 on `lib/` wording, fixed.
- Architect, security, and high-level-advisor voted Accept in round 1. Round 2 changed no finding they raised to a worse state.

## Open items outside this change

- The smoke's guard negative control no longer proves anything, because `stuck-detection` rates `safe` at the pin. The seven skills excluded as dangerous rest on older guard runs.

## After consensus

- The frontmatter `date` moved from 2026-11-15 to 2026-11-24, as the doc-date-drift check asked. No decision text changed.
