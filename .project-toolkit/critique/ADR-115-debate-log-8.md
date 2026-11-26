# ADR Debate Log: ADR-115 Hermes Fourth Pack (D11)

## Summary

- **ADR**: `.project-toolkit/architecture/ADR-115-native-plugin-support-per-host.md`
- **Prior debate log**: `.project-toolkit/critique/ADR-115-debate-log-7.md` (closed by consensus; not edited)
- **Trigger**: owner decisions, Richard, 2026-11-19, in the D10 implementation session. Asked whether knowledge relief should ride in the unmerged D10 change so Hermes users migrate once, he answered yes. Offered two layouts for the six skill-authoring skills, he chose B, a fourth pack, over A, moving them into quality.
- **Panel**: full (architect, critic, independent-thinker, security, analyst, high-level-advisor). The amendment changes the pack table the build reads and the smoke's `--force` allow list.
- **Implementation under review**: commit `48ec974f3`, parent `c87c838dd`. Follow-ups: `3811d3d68` wraps two lines over 100 columns; `62d7aa7d9` adds smoke script cases and updates the install guide.

## Pre-review evidence

- Measured 2026-11-19 at `9693b793`: knowledge held 386 files against `packMaxFiles: 399`, 13 free.
- Measured 2026-11-19 at `c87c838dd`: knowledge's largest group joined by script or reference paths holds 130 skill files in six skills; the next holds 56. The six link to each other through `skillforge`.
- Measured 2026-11-19 at `48ec974f3`: delivery 297 files and 42 skills, knowledge 256 and 34, quality 163 and 14, authoring 186 and 6. No skill file lost, gained, or changed; 55 identical `lib/` files in all four packs. `build_all.py --check` exits 0 with Hermes drift 0.
- Pinned guard (hermes-agent `63d0b94`) at `48ec974f3`: delivery `caution` with 10 reviewed `high` findings, authoring `caution` with the two reviewed `skillforge` findings, knowledge and quality `safe`.
- No-force install at the pin, 2026-11-19: quality and knowledge installed; authoring (99 findings) and delivery (278) printed `Decision: BLOCKED`.
- Option A, measured 2026-11-19 on a copied tree: quality plus the six holds 293 files and rates `caution` with the two `skillforge` findings.
- Real Hermes smoke at the pin, 2026-11-19, at `48ec974f3`: 9 passed.

Logs for these sit in the session scratch folder `.project-toolkit/scratch/d10/` (`panel/verify-move-d11.txt`, `panel/guard-d11.txt`, `panel/noforce-install-d11.txt`, `panel7/knowledge-groups-c87.txt`, `panel7/optionA-guard.txt`, `smoke-d11.log`, `build-check-d11.log`).

## Round 1

Each seat reviewed independently and wrote its own file.

| Agent | Vote | P0 | P1 |
|-------|------|----|----|
| architect | Accept | 0 | stale D10 Negative bullet ("three packs", "13 free files"); undo steps omit the parity script and tests |
| critic | Accept | 0 | none; six P2 |
| independent-thinker | Disagree-and-Commit | 0 | stale D10 Negative bullet |
| security | Disagree-and-Commit | 0 | the guide's stale-check step forces a reinstall with no findings read |
| analyst | Disagree-and-Commit | 0 | `prompt-engineer` claim false for Hermes (the mention is frontmatter `metadata`, which Hermes drops) |
| high-level-advisor | Disagree-and-Commit | 0 | the migrate-once rationale was never run; owner to choose run or accept |

REFUTED claims: `prompt-engineer` names `prose-self-check` (analyst, architect, critic, independent-thinker).

### Changes made after round 1

- Removed the `prompt-engineer` clause.
- The D10 Negative bullet now says three packs "until D11" and 13 free files "at `9693b793`".
- Undo D11 now says revert `48ec974f3`, naming the parity script, six test files, and the smoke's new script cases. The D10 force-policy undo clause now names any other `caution` pack.
- Ran the reinstall the high-level-advisor asked for, at the pin, from local copies (`panel7/reinstall-probe.txt`). Over an `ae5acffcb` two-pack install, a forced reinstall left delivery with 42 skills (was 56) and knowledge with 34 (was 40). Adding quality and authoring listed 96 skills with no duplicate name. A no-force reinstall of an installed `SAFE` pack stops with "already exists".
- Install guide: the update and stale-check steps read findings first, then use `--force`, which any reinstall needs. Claims are narrowed to what ran: a local `file://` source with `--no-enable`. The guide names the two authoring findings.
- The ADR states why this group moved (largest group; holds knowledge's only `high` findings), the force count under either option, and the cost of a fourth `lib/` copy.
- Alternatives add the smaller `business-strategy` plus `decision-critic` move and rewording the two `skillforge` lines.
- `retrospective` now reads "tells the agent to run" `distill_artifact.py`, "with no fallback".
- The smoke now runs a script with only the plugin root in every pack, plus a no-lib negative control: knowledge `chestertons-fence/scripts/investigate.py`, authoring `prose-self-check/scripts/prose_lint.py`. 13 passed (`smoke-d11b.log`).
- Saved the missing logs: the group sizes, option A's guard result, and the largest packed group at `3811d3d68` (150 files in 12 skills).

### Deferred P1 items

None.

## Round 2

Each seat checked its own round 1 items and the changed text against primary sources.

| Agent | Vote | Position |
|-------|------|----------|
| architect | Accept | All round 1 items resolved except the undo text. New P2: "revert `48ec974f3`" conflicts at HEAD in four files (tried in a throwaway worktree), and the smoke script cases came from `62d7aa7d9`; "not run" clause in the D10 bullet is stale. |
| critic | Disagree-and-Commit | Five of six items resolved. New P1 N1: undo by SHA fails, because `main` squash-merges, the revert conflicts, and the smoke cases are in another commit. P2: stale "not run" clause; claimed the ADR lacks the 150-file figure. |
| independent-thinker | Accept | Six of seven items resolved; debate log 7 must exist before commit. P2: undo names the wrong commit; "installed three packs until D11" never happened, since D10 never released. |
| security | Accept | All six items resolved; the stale-check order is safe, because a no-force run of an installed `CAUTION` pack still prints its findings. P2: reinstall ran from a local source only; branch ruff ratchet is +2, unchanged since `c87c838dd`. |
| analyst | Disagree-and-Commit | All five items resolved; every count matches its log. P2: stale "not run" clause; undo names the wrong commit; the Update step's "if you accept any findings" misfits a `SAFE` pack. |
| high-level-advisor | Accept | The P1 is resolved by the reinstall run. P2: stale "not run" clause; undo should drop the SHA, since `main` squash-merges. No owner decision blocks the merge. |

### Edits after round 2

- Undo D11 is described by content, with no commit SHA: move the six skills back, delete the `authoring` row, move the two `skillforge` entries back, drop the authoring manifest from the parity script, point each test that names `project-toolkit-authoring` back at knowledge, and drop the smoke's authoring script case. This is the critic's proposed fix for N1 and closes the P1.
- The D10 Negative bullet says "D10 planned three packs, and D11 replaced that plan before release", and the reinstall "was not run until D11".
- `retrospective` "tells the agent to run a script they lack" in the D11 Negative bullet.
- Install guide Update step: `--force` is needed to replace any installed pack, even a `SAFE` one; for a `CAUTION` pack, force only after accepting the findings.
- The reinstall probe log now records the hermes-agent commit it ran: `63d0b94120027d487c9a5235b9ec64b696af1b26`.

These narrow claims and change no rule, so no further round ran.

### Claims checked by the author after round 2

- Critic N3 is REFUTED: the Packs bullet (ADR line 117) reads "Measured 2026-11-19 at `3811d3d68`, the largest group of packed skills joined by script or reference paths holds 150 files in 12 skills, and it fits."
- The round 1 disposition said pre-PR had 3 failing gates. The summary JSON shows 116 PASS, 5 FAIL, 2 SKIP at both `c87c838dd` and `3811d3d68`, with the same validators: Count Ratchets (ruff +2 from merge `07a69ff6e`), Python Duplicate Code Detection, IO Portability, and two advisory gates. The independent-thinker caught the count.

## Owner questions

None open. The owner chose knowledge relief in this change and option B. The Hermes CI leg stays a Deferred Item from log 6.

## Outcome

Outcome: Consensus in round 2, four Accept and two Disagree-and-Commit, no P0 or P1 open. Dissent recorded: the critic and analyst seats commit after asking for the undo text to be described by content, which the post-round edits do. The ADR stays `proposed`.

### P2 items left open

- The reinstall ran from a local `file://` source with `--no-enable`, not from GitHub with `--enable` (security). The guide says so.
- No workflow runs the Hermes smoke (carried from log 6).
- Installing a new pack before reinstalling an old one puts one skill name in two packs; untested. The guide orders the steps to avoid it.

## Coordination

A sibling worker owns `fix/readiness-d11-duplicates`. At `1f4d972a6` it changes `doc_accuracy.py` in every tree and adds tests; it adds no file under `src/`, so every pack count above holds, and `git merge-tree` with this branch reports no conflict. A shared `lib/` file it adds later costs one slot in each of the four packs; the smallest headroom is delivery's 102.
