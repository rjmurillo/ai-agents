# ADR Debate Log: ADR-115 Hermes Third Pack (D10)

## Summary

- **ADR**: `.project-toolkit/architecture/ADR-115-native-plugin-support-per-host.md`
- **Prior debate log**: `.project-toolkit/critique/ADR-115-debate-log-5.md`
- **Trigger**: owner decision D10, Richard, 2026-11-19, relayed in the readiness integration session. Merging `origin/main` at `ae5acffcb` into the readiness branch left `project-toolkit-delivery` at 404 files against `packMaxFiles: 399`. The owner chose "add a third pack" over "rebalance the two packs".
- **Panel**: full (architect, critic, independent-thinker, security, analyst, high-level-advisor). The amendment changes executable enforcement: the pack table the build reads, and the smoke's `--force` policy.
- **Implementation under review**: commit `9693b7932b3eb6211613f32fca478fa72ee865be`, parent `07a69ff6e`.

## Pre-review evidence

- Measured 2026-11-19 at `07a69ff6e`: `build_all.py --check` failed with one error, `pack project-toolkit-delivery has 404 files; packMaxFiles is 399`.
- Measured 2026-11-19 at `9693b793`: delivery 297 files and 42 skills, knowledge 386 and 40, quality 163 and 14. No skill file lost, gained, or changed; 55 `lib/` files identical in all three packs. `build_all.py --check` exits 0.
- Pinned guard (hermes-agent `63d0b94`) at `9693b793`: delivery `caution` with 10 `high` findings, knowledge `caution` with 2, quality `safe`. Knowledge was already `caution` on `origin/main` at `ae5acffcb` and `safe` at `0982e4fe7`.
- Real Hermes smoke at the pin, run 2026-11-19: 9 passed. Before the force-policy change every test errored, because the old rule allowed `--force` for delivery only.

## Round 1

Each seat reviewed independently and wrote its own file. No seat saw another's review.

| Agent | Vote | P0 | P1 |
|-------|------|----|----|
| architect | Disagree-and-Commit | 0 | A1 wrong alternative named ("budget raise"); A2 Packs bullet contradicts the new move rule; A3 Reversibility not amended |
| critic | Disagree-and-Commit | 0 | conflicting remedies in the Packs bullet; no knowledge headroom plan; cross-pack rule says more than the build checks; force list never runs automatically; reinstall drop stated as fact but not run |
| independent-thinker | Disagree-and-Commit | 0 | stale "255 files" count; knowledge runs out next with no plan; install guide claim about `/test` refuted (`security-scan`) |
| security | Disagree-and-Commit | 0 | F1 no workflow runs the smoke, so a new high finding merges green; F2 the guide's update step uses `--force`, which accepts any new caution finding |
| analyst | Disagree-and-Commit | 0 | none; five P2, including unlogged measurements and the stale `stuck-detection` reason |
| high-level-advisor | Disagree-and-Commit | 0 | wrong alternative named; stale remedies in the Packs bullet; no split trigger; "no file changed" refuted (manifests changed) |

No claim was REFUTED except: the `/test` sentence in the install guide (independent-thinker), "255 files" (independent-thinker), and "No skill, file, ... changed" (high-level-advisor).

### Changes made after round 1

- The Split bullet says a raise could not clear 404 at a 400 cap and names rebalancing as the offered alternative. Alternatives Considered adds rebalancing and the smaller 17-skill split.
- The Packs bullet gives two remedies with their cost: a raise up to 400, or a move or new pack under an amendment with the full panel.
- Negative consequences and the Reversibility Assessment gain 2026-11-19 paragraphs.
- The build-fail list states the exact path check. The guard rule moved out of that list, because the smoke runs the guard, not the build.
- The Split bullet names the prose cross-pack mentions a single-pack user sees.
- The Smoke bullet says no workflow runs the smoke, that the Decision 10 CI leg is still missing, and that line churn is the accepted cost of rejecting moved findings.
- "255 files" became a dated 150 files in 12 skills at `9693b793`.
- "No skill, file" became "no skill file, `lib/` module, exclusion, or budget", naming the two manifest changes.
- Install guide: the update step reinstalls without `--force` first; the `/test` sentence names `security-scan`; the reinstall drop is marked not run, with a count check.
- Logs added under the session scratch folder for the guard history, the move check, and pack counts.

### Deferred P1 items

- **Split trigger for knowledge (critic, independent-thinker, high-level-advisor).** Setting a trigger is the owner's call under User Sovereignty, and the owner set "no earlier trigger" on 2026-11-15. Since then `origin/main` raised `packMaxFiles` five times, from 381 to 399, on 2026-11-17 and 2026-11-18 (`031b40d48`, `57feafaed`, `4f8e3852a`, `498d4892a`, `d374ae9c1`). The ADR now states that knowledge has 13 free files and reaches the budget first. Deferred to the owner.
- **Hermes CI leg (critic, security F1).** Decision 10 already requires it; it predates D10 and is outside its scope. The ADR now states it is missing.

## Round 2

Each seat checked its own round 1 items and every claim in the changed text against primary sources.

| Agent | Vote | Position |
|-------|------|----------|
| architect | Accept | A1, A2, A3 resolved. P2: the 398 and 392 rebalance figures have no log; the reinstall loss is stated as fact; the frontmatter date is stale. |
| critic | Disagree-and-Commit | Three P1s fixed; the knowledge trigger and the CI leg are deferred with reasons. P2: the CI leg is not under Deferred Items; "failed every smoke run" is too broad, since knowledge is `safe` at `0982e4fe7`; the reinstall loss and the 398 and 392 figures are not measured; D10 has no record outside the session. |
| independent-thinker | Accept | All three P1s resolved or deferred. P2: the reinstall loss; the rebalance figures; knowledge growth rate (333 to 386 files in 30 days) not stated; "four rules" lists three. |
| security | Disagree-and-Commit | F2 resolved; F1 deferred as P2, because the ADR states the missing CI leg. P2: the reinstall loss; the `/test` list reads as complete. |
| analyst | Accept | No REFUTED claim; round 1 UNVERIFIED claims now verified from the new logs. P2: the reinstall loss; the `/test` list; the 150-file and rebalance figures have no saved output; `spec` fills two sections from quality skills. |
| high-level-advisor | Accept | Three P1s fixed; the trigger deferral is recorded. Open owner question: whether knowledge relief should ride in this change so users migrate once. |

### P2 wording edits after round 2

These narrow claims and change no rule, so no further round ran.

- The reinstall loss now reads as "the new delivery pack no longer carries 14 skills", with the reinstall marked not run.
- The 398 and 392 figures are gone; the eight-file total follows from 404 plus 386 against two budgets of 399.
- "Four rules" became three rules plus the headroom aim.
- The `/test` sentence names its skills as examples, not the full list.
- "Failed every smoke run" now names `ae5acffcb` and `07a69ff6e`.
- Deferred Items lists the knowledge trigger and the Hermes CI leg.
- The frontmatter `date` is 2026-11-19.
- The Packs bullet and Negative consequences no longer restate the panel size; `AGENTS.md` owns that rule.
- The deferral entry gains the budget history.

## Owner questions

- Set a trigger for the next Hermes split or move, given knowledge has 13 free files at `9693b793`?
- Should knowledge relief ride in this unmerged change, so Hermes users migrate once?

## Outcome

Outcome: Consensus in round 2, four Accept and two Disagree-and-Commit, no P0 or P1 open. Dissent recorded: the critic and security seats commit with the Hermes CI leg still missing, so the force allow list is checked only by a local smoke. The ADR stays `proposed`.
