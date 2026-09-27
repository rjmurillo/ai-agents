# ADR-111 Debate Log

ADR: `.project-toolkit/architecture/ADR-111-skill-model-pins-project-per-harness.md`.
Issue: #5606. Date: 2026-09-27.

## Format

The operator caps fan-out at three subagents. The six seats ran as two
agents with three seats each. Seat A held architect, critic, and
high-level-advisor. Seat B held independent-thinker, security, and analyst.
Each read the ADR, ADR-080, issue #5606, and the implementation diff.

## Phase 0: related work

Issue #5606 and the ADR-080 Amendment 2026-08-12 finding 4 frame the gap.
Issue #5605 closed the seventh case (`research`). Issue #5313 removed the
agent default model. No open pull request touched the same files.

## Round 1: independent review

| Seat | Verdict | Findings |
| --- | --- | --- |
| architect | Disagree-and-Commit | P1 filing state; P2 declared `frontmatterDrop` not listed; P2 capability row |
| critic | Disagree-and-Commit | P1 one-sided trade-off; P2 evidence stronger than stated; P2 "changes only rule 3"; P2 no review trigger |
| high-level-advisor | Accept | P2 open agent question needs a follow-up |
| independent-thinker | Accept | P2 cite more sources; P2 label "intent is lost" INFERRED; P2 tripwire |
| security | Disagree-and-Commit | P1 blank line in a block scalar corrupted the next key; P2 un-indented list; P2 spaced or quoted key |
| analyst | Accept | P2 rule 3 heading read backwards |

No P0. Both seats confirmed the seven-skill list, the empty Copilot grep,
`check_model_pins.py --mode enforce` exit 0, and the agent carve-out.

## Resolution

- **Security P1, fixed.** The regex cut was replaced by a line walk that keeps
  blank lines inside a block scalar with the value. A parse-and-compare guard
  raises `ValueError` if any other key changes. The un-indented list, spaced
  key, and quoted key cases are handled and tested.
- **Architect P1, fixed.** ADR-111 moves to `accepted` in the same change
  that flips ADR-080. The pull request carries both flips, so a declined PR
  leaves ADR-080 accepted. `check_adr_lifecycle.py` forbids a proposed record
  from superseding, which confirms this shape.
- **Critic P1, fixed.** A Negative consequence now names the Claude Code
  per-turn override.
- **Architect P2, adopted.** The drop is now the declared
  `artifacts.skills.frontmatterDrop` key, the same key the rules stanza uses.
- **Critic and independent-thinker P2s, fixed.** Three evidence sources are
  cited and graded runtime-unverified. The "changes only rule 3" line now
  says rules 1, 2, 4, 5, and 6 are restated. `review-by: 2027-03-27` added,
  with a trigger on Copilot schema changes. The Context labels the intent-loss
  sentence INFERRED.
- **Analyst P2, fixed.** Rule 3 now reads "Versioned ids are never minted
  from rolling aliases".
- **Architect P2 capability row, not adopted.** The agent-harness-reference
  `probe-evidence.md` file records runtime observations only, and no runtime
  probe ran. The row belongs there once one does.
- **High-level-advisor P2, recorded.** The generated-agent `haiku` question
  is flagged in the pull request body for the owner. It is not filed as an
  issue without owner authorization.

## Round 2: convergence

Both seat agents re-read the revised ADR, this log, and the diff.

| Seat | Verdict | Note |
| --- | --- | --- |
| architect | Accept | P1 resolved; new P2: four reformat-only build scripts |
| critic | Accept | P1 resolved at the Negative consequence |
| high-level-advisor | Accept | Agent `haiku` question flagged, not filed |
| independent-thinker | Accept | Three sources, graded runtime-unverified |
| security | Accept | 13 edge inputs re-run; two malformed inputs now raise |
| analyst | Accept | Rule 3 wording fixed |

Consensus: 6 of 6 Accept. The new P2 was fixed: the four reformat-only files
were reverted. Security accepts one residual gap: frontmatter that is not
valid YAML skips the guard, and the skill validators own that input.

## Post-consensus edit

The test-gate review found that rule 6 overclaimed: it read as if
`check_model_pins.py` enforced rule 3's projection clause, but the scanner
does not read generated mirrors. Rule 6 now names the checks that do:
`tests/build_scripts/test_copilot_skill_model_projection.py` and
`build_all.py --check`. The edit narrows a claim and changes no rule, so no
new vote round ran.

The `/review` code-quality axis then flagged a cohesion drop in
`copilot_body_translation.py`. The key-drop code moved to its own module,
`build/scripts/frontmatter_key_drop.py`, and the Impact table names it. No
rule changed.

ADR-080's supersession note was shortened to keep the file at 500 lines,
under the taste file-size ceiling. The note keeps the successor and scope.
