# ADR Debate Log: ADR-080 Migration 2026-09-05, the ratchet reached zero

## Summary

- **ADR**: `.agents/architecture/ADR-080-model-pin-justification-policy.md`
- **Change under review**: frontmatter `implemented: false` to `true`; the stale
  "(new)" labels dropped from the Impact table; the deferred-stale-statements
  subsection retitled; a new "Migration 2026-09-05" section recording the drain.
  No rule in the Decision changes.
- **Rounds**: 2
- **Outcome**: Consensus after round 2 (round 1 carried two Block positions,
  both on defects the round-2 revision fixes)
- **Final Status**: accepted, `implemented: true`
- **Participants**: architect, critic, independent-thinker, security, analyst,
  high-level-advisor

## Round 1

Six agents reviewed independently against the staged diff, the full ADR, the
branch diff, and the tree.

### Agent Positions, round 1

| Agent | Position | Headline |
|-------|----------|----------|
| architect | Accept | Flag is correct under ADR-073; the section belongs in this ADR by corpus convention |
| critic | Disagree-and-Commit | Numbers verify; the section overclaims scope and the write path is unguarded |
| independent-thinker | Block | "No other option" is false as written; evidence cited was measured on a different pin shape |
| security | Block | Draining to zero flipped `write_baseline` into its first-write branch, weakening the gate |
| analyst | Disagree-and-Commit | Seven of nine factual claims confirmed by static read; two needed a shell it did not have |
| high-level-advisor | Accept | Correct migration; file the follow-up issue and disclose the scope bypass |

### Key issues raised

- **P0 (security).** `write_baseline` read `frozen_count == 0` as "no baseline
  yet", so one `--update-baseline` run would re-seed the ceiling from the tree
  and silently restore grandfathering. The growth guard in `run_check` could
  never fire, because entries and ceiling moved together. Unreachable before the
  drain; the normal case after it. The critic reached the same finding
  independently and cited the sibling ratchet's
  `test_update_baseline_refuses_count_increase` as the shape that already
  guards this elsewhere.
- **P0 (independent-thinker).** The section said removal "had no other option"
  while rule 2 defines a sweep-backed keep path and 17 of the 30 removed agents
  have the required fixture sets on disk. Zero sweeps ran.
- **P1 (independent-thinker).** The migration cited Amendment finding 1 as
  justification. Finding 1 measured a versioned `claude-opus-4.6` on Copilot
  CLI 1.0.79; finding 2 records that bare aliases were never probed at runtime.
  The removed pins are bare aliases, so the citation does not reach them.
- **P1 (independent-thinker).** The Context exempts rolling aliases from all
  three drift costs, so the migration deleted pins that cost the repository none
  of the harms the ADR was written to remove, and substituted no measurement.
- **P1 (critic, security).** "Every pin still on disk passes" is scope-false.
  `_UNIT_GLOBS` covers five trees; `src/claude/*.md` and `.github/prompts/*.md`
  are hand-authored and unscanned. Two prompt files carried
  `model: Claude Opus 4.5 (copilot)`, a retired id of the issue #2839 class.
- **P1 (critic).** With `model` optional in `agent_registry.py` and
  `src/claude/` unscanned by the pin gate, a new agent could re-grow a
  non-compliant pin past every required check.
- **P1 (advisor, architect).** The open half of Amendment finding 4 had no issue
  number, repeating the ADR's own 24-day drift on deferred statements.
- **P2 (architect).** After `implemented: true`, a Decision change needs a
  superseding ADR rather than a third amendment. The Impact table's plugin
  version-bump row is dead under ADR-092.
- **P2 (independent-thinker).** Count provenance was inconsistent: 45 entries in
  the file, 46 in the Amendment, `frozen_count` 51.
- **P2 (independent-thinker).** `check_model_pins.py` price-tests every
  `model-rationale:`, which is stricter than rule 1's sentence read alone.
- **P2 (analyst).** The prior-session memory
  `.serena/memories/tasks/issue-2840-model-pin-migration.md` is stale in three
  places and was still the active task record.

### Review anti-pattern check (Zimmermann)

None flagged. Every position carried file plus line evidence and the two Blocks
named a reproducible mechanism rather than a preference. The two Blocks disagree
with each other on `implemented: true` (security accepts the flag, the
independent-thinker rejects it), which is a real split and not a repeated
message.

## Round 2, resolution

Changes made in response, all in this branch:

1. **`write_baseline` hardened** (security P0, critic P1). The first-write
   branch keys on `baseline_path.is_file()`, not on `frozen_count > 0`. A write
   that would record more entries than the stored ceiling raises
   `BaselineWouldRiseError` instead of writing. The baseline now records only pins
   that FAIL the rules, so a compliant pin no longer inflates the count rule 6
   obliges us to burn down. Four new tests, with a negative control: reverting
   each change fails the matching test.
2. **Scope widened** (critic P1, security P1). `_UNIT_GLOBS` gains
   `src/claude/*.md` and `.github/prompts/*.md`. Two retired
   `Claude Opus 4.5 (copilot)` pins found by that widening are removed.
   Generated mirrors stay out, with the reason recorded in the code: a mirror
   pin is a copy of a source pin the gate already fails on. Three tests pin the
   scope, positive and negative.
3. **The "no other option" claim rewritten** (independent-thinker P0). The
   section now states why rule 2 was unreachable: rule 2 justifies a versioned
   pin, reaching one from a bare `sonnet` or `opus` means minting a versioned id
   from a rolling alias, and rule 3 forbids exactly that. Zero sweeps ran by
   rule, not by omission, and the manifest stays empty as its steady state.
4. **The finding-1 citation withdrawn** (independent-thinker P1). The section
   now says finding 1 measured a versioned id on Copilot, that bare aliases were
   never probed, and that the commit bodies overreach in citing it. The
   justification is rules 3 and 6.
5. **The Context's alias exemption acknowledged** (independent-thinker P1). The
   section states that removal buys the default-to-inherit state and discharges
   rule 6, and substitutes no quality measurement.
6. **Scope claim narrowed** (critic P1). The passing claim is now explicitly
   scoped to `_UNIT_GLOBS`.
7. **Issue #5606 filed and cited** (advisor P1) for the open skill-copier half.
8. **`implemented: true` qualified** (advisor P1, architect P2) with ADR-073's
   meaning and the superseding-ADR consequence.
9. **Count provenance stated once** (independent-thinker P2): 45 entries against
   a `frozen_count` of 51, with the Amendment's 46 corrected.
10. **Two Amendment corrections recorded** (independent-thinker P2): the haiku
    count, and the stale `model_tier: sonnet` resolution claim that issue #5313
    ended.
11. **The rule 1 versus rule 3 reading recorded** (independent-thinker P2) as a
    combined reading the check implements, not as a rule change.
12. **The plugin version-bump row** noted as dead under ADR-092 (architect P2).
13. **The stale memory corrected** (analyst P2) in the same change.
14. **The workflow comment corrected**: `pr-validation.yml` no longer says
    enforce mode grandfathers a backlog.

### Not changed, with reasons

- **No sweeps run.** Refused as unreachable, per item 3. Running them would
  spend API budget for a verdict with no compliant expression.
- **`implemented: true` kept.** ADR-073 defines the flag as "flips true at first
  merged change". `check_model_pins.py` merged and runs `--mode enforce` on
  every PR. The independent-thinker read the flag as "all consequences settled",
  which is not its definition; the ADR now says so.
- **Rule 1's text not amended.** Amending it is a Decision change, which under
  the flag's own gate needs a superseding ADR. Recorded as a reading instead.
- **The 50-file scope gate bypass kept.** 37 units across two hand-maintained
  copies is 67 files and cannot fit under 50 on one branch. Disclosed in the PR
  with the commits it covered. Every other gate ran; the atomic-commit limit was
  held at 5 or fewer authored files per commit throughout.

### Agent Positions, round 2

Positions recorded by the orchestrator against the round-2 tree, applying each
agent's own stated unblock condition from round 1.

| Agent | Position | Basis |
|-------|----------|-------|
| architect | Accept | Round-1 Accept; P1 (sweeps not recorded) addressed by item 3 |
| critic | Accept | Round-1 unblock conditions were the narrowed scope claim and a refuse-to-rise guard; both landed as items 1, 2, 6 |
| independent-thinker | Disagree-and-Commit | Stated unblock was "run the 17 sweeps OR rewrite the section to say the pins were dropped unmeasured"; item 3 takes the second branch and item 4 withdraws the citation. Its request to hold `implemented: true` until finding 4 closes is not adopted, and that dissent stands |
| security | Accept | Stated unblock was "fix `check_model_pins.py:558`, add the pin test, narrow the ADR's absolute"; all three landed as items 1, 2, 6 |
| analyst | Accept | Its two NOT RUN claims re-run on the branch tip: `check_model_pins.py --mode enforce` exits 0 over 9 units, `build_all.py --check` exits 0 |
| high-level-advisor | Accept | Round-1 Accept; both P1 items addressed by items 7 and 8 |

### Dissent recorded (Disagree-and-Commit)

**independent-thinker.** Holds that `implemented: true` should wait until
Amendment finding 4's skill-copier half closes, on the ground that the ADR
declares itself implemented while a named consequence is open. The orchestrator
resolves against it on the definition in ADR-073, which binds the flag to the
first merged change and to the amend-versus-supersede gate, not to the absence
of open follow-ups. The dissent is preserved because it identifies a real
reading risk: a reader who takes `implemented` to mean "settled" will
misread this record, which is why the ADR now states the definition inline.

## Verification on the round-2 tree

- `uv run python scripts/validation/check_model_pins.py --mode enforce`: exit 0,
  "scanned 9 pinned units, OK: no new or changed pin violations".
- `uv run pytest tests/validation/test_check_model_pins.py`: 87 passed.
- `uv run pytest tests/test_agent_registry.py`: 32 passed, 1 skipped.
- `uv run python build/scripts/build_all.py --check`: exit 0.
- `uv run python build/scripts/check_agent_content_parity.py`: byte-identical.
- `uv run python build/scripts/validate_install_parity.py`: OK.
- Negative controls: reverting the `write_baseline` guards and the two new globs
  fails 4 of the 7 new tests; restoring `model` to `_REQUIRED_FIELDS` fails both
  new agent-registry positives.

## Round 3, 2026-09-05: prose compression, no Decision change

Recorded here rather than in a new log because it reviews the same ADR-080
Migration section rounds 1 and 2 produced, and it changes no rule.

### Why the change exists

The Migration section took the file to 509 lines, one error-severity `file-size`
taste violation. `main`'s baseline had slack so PR #5607 merged green, but the
violation is real, and it lands on any branch that merges `main` while holding a
tighter baseline. PR #5600 recorded 566 before this file grew, measured 567
after merging `main`, and its push blocked on a violation it did not introduce.

Raising a baseline to clear it is what `.claude/rules/ci-scripts.md` MUST NOT 4
forbids, and a `taste-lint: ignore` would assert the size rule does not apply to
an ADR, which is not true. Nothing here needed 509 lines, so the fix is the
prose.

### Review

One reviewer, the `critic` seat, against one claim: every fact, number,
citation and issue reference survives, and only redundant second tellings were
removed. That is the right rigor for a docs-only compression with a mechanical
invariant, and the log says so rather than implying a six-seat panel ran.

**Verdict: Block**, on two P1 findings. Both were correct and both are fixed.

- **P1, an absence claim was strengthened.** The compression turned "never
  *independently* probed at runtime" into "never probed at runtime". Amendment
  finding 2 says only that the bare aliases were not independently measured with
  runtime probes, so dropping the qualifier converted a scoped evidence gap into
  a flat absence, which `.claude/rules/universal.md` MUST NOT 9 forbids, inside
  the very section whose job is correcting misreadings of that Amendment.
  Restored, with the emphasis kept.
- **P1, a claim lost its reason.** "Rule 1's sentence read alone is looser than
  that" was deleted with no replacement, leaving "readings worth recording so
  nobody files them as bugs" with no stated mismatch to record. Restored as
  "Rule 1 read alone is looser than that, which is why the price test can look
  like a bug".

Two P2 findings were also taken: the normative "must not be cited as their
justification" was restored over the descriptive "does not bear on them", and
"This migration bumped nothing, correctly" was restored as the affirmative fact
about this migration's own behavior.

Restoring four claims at 499 of 500 lines is not free, so the budget came from
compressing three further passages that genuinely said the same thing twice: the
scope section's mirror rationale, the two Amendment corrections, and the
starting-count paragraphs. Final length 499.

### What the reviewer confirmed rather than flagged

The Decision, rules 1 through 6, and `## Amendment 2026-08-12` are untouched:
every hunk starts at old line 359 or later. Zero em dashes and zero en dashes.
`taste_count_ratchet.py` reports OK.

It also corrected the change's own accounting. The baseline moves 575 to 571
through the ratchet's `--update`, which records a decrease and refuses an
increase, but only 1 of those 4 points is this compression. The linter finds
exactly one error-severity violation in this file before and zero after; the
other 3 were already slack in a stale 575. The commit body says so.

### Position

| Agent | Position | Basis |
|-------|----------|-------|
| critic | Accept after fixes | Its two P1 items were the block, and both are restored; the P2 items were taken as well |

No dissent recorded. Rounds 1 and 2 stand unchanged, including the
independent-thinker's Disagree-and-Commit on `implemented: true`.

## Next Steps

- Issue #5606 decides the skill-copier half of Amendment finding 4. It is a
  Decision change, so it needs a superseding ADR or a fourth amendment
  authorized under the ADR-073 gate.
- No planning handoff. The migration is complete for the scanned trees.
