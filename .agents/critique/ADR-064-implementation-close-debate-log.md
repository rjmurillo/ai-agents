# ADR-064 debate log: flipping to accepted and implemented

Subject: `.agents/architecture/ADR-064-commands-to-skills-migration.md`,
frontmatter `status: proposed` to `accepted` and `implemented: false` to `true`,
plus the matching `## Status` prose and a new `## Implementation Outcome` section.

Gate: `AGENTS.md` fires `adr-review` on any `ADR-*.md` edit, and
`scripts/validation/git_hook_policy.py check_adr_review_policy` refuses the
commit without this log staged alongside it.

Branch: `claude/5632-commands-to-skills`. Issue #5632. Ran 2026-09-08 against the
branch head, with the six `adr-review` roles invoked as subagents in parallel,
each given the same narrow question and told to cite file paths and verify
against the tree rather than the ADR's prose.

## Result

Six votes: 2 ACCEPT, 1 DISAGREE-AND-COMMIT, 3 BLOCK. Not consensus, so the blocks
were cleared before the flip landed rather than overridden.

| Role | Verdict | One-line reason |
|---|---|---|
| security | ACCEPT | The CWE-829 trust boundary still fails closed after the config move: no orphaned copy survives, all three path literals agree, the new guard fails closed, and install-trust never keyed on the path segment. |
| high-level-advisor | ACCEPT | Flip inside this PR; the ADR-status edit is part of the same diff that makes the claim true, and splitting it leaves main carrying a completed migration with a lying ADR. |
| independent-thinker | DISAGREE-AND-COMMIT | The retirement is verified real, so flip it, but the ADR still names four `forgetful-*` skills that were decommissioned rather than migrated, and #5632's "no behavior change" premise is contradicted by every migrated skill's frontmatter. |
| architect | BLOCK | Decision item 4 and Implementation Notes step 7 did not ship as written and the Consequences and Impact sections were not corrected, so `implemented: true` overstates the record. |
| critic | BLOCK | `CLAUDE.md`'s own "Lifecycle commands" section still framed the migrated skills as "slash commands (not skills)", which is the two-surface confusion the ADR exists to remove, in the one file every session loads. |
| analyst | BLOCK | Step 7 measurably incomplete: nine `.claude/commands` citations remained across `tests/commands/` and `tests/evals/spec-scenarios.json`. |

## What the blocks found, and what was done

Each finding was verified against the tree before acting on it. None was
dismissed.

1. **`forgetful/*` was decommissioned, not migrated** (architect, critic,
   independent-thinker). Confirmed: `.claude/skills/forgetful-*` does not exist,
   `.claude/commands/forgetful/` was already absent from `origin/main` before
   this branch started, and `tests/skills/test_forgetful_decommission_guards.py`
   records the retirement under issue #5574. The ADR's Decision item 4 and
   Implementation Notes step 4 were left verbatim as the decision of record and
   the divergence is stated in the new `## Implementation Outcome` section.
   Rewriting a decision to match its outcome destroys the thing an ADR is for.

2. **`CLAUDE.md` contradicted the ADR** (critic). Confirmed at the "Lifecycle
   commands" section, which read "use slash commands (not skills)" and listed six
   phases that are all skills on this branch. The ADR's own Impact table named
   this file as requiring the update. Rewritten to "Lifecycle skills", with a
   sentence saying `/spec` still types the same because Claude Code fires a
   `user-invocable` skill by name.

3. **Stale inventory** (critic, architect). Confirmed: the ADR's "Top-level (11)"
   and "22 commands" were measured on 2026-06-01, and `checkpoint`, `retro` and
   `sync` landed afterwards, so 14 top-level plus 7 `pr-quality/*` is 21
   converted. Recorded in the outcome section with the reason a count in a
   Context section is a measurement of a commit rather than a permanent fact.

4. **Step 7 incomplete** (analyst, architect). Confirmed and fixed. The nine
   remaining citations were re-keyed: five `tests/commands/` modules whose
   docstrings named `.claude/commands/spec.md` as the canonical source of a
   contract they mirror, and the two scenario inputs in
   `tests/evals/spec-scenarios.json`.
   `tests/commands/test_lifecycle_command_drift.py` was deleted rather than
   re-keyed: its discovery glob had gone empty, so it was passing vacuously, and
   its subject was the markdownlint MD041 exemption that lifecycle commands
   needed for having no H1, which a skill has by construction.

5. **A live defect the debate surfaced by accident.** Chasing the analyst's
   citation list found that `find_scenarios_for_prompt` in `scripts/eval/eval-suite.py`
   derived the scenario name from the file stem, which is the useless constant
   `SKILL` for every skill body. The convention resolved for
   `.claude/commands/spec.md` and returned `None` for
   `.claude/skills/spec/SKILL.md`, so every converted prompt was silently
   unrouted. Fixed to read the directory name for a `SKILL.md`, and probed by
   reverting the branch: the discovery test fails under the old form and passes
   under the new one. CI did not catch this because the workflow passes
   `--scenarios` explicitly.

6. **The migration is not behavior-neutral** (independent-thinker). Confirmed:
   `grep -rl disable-model-invocation .claude/skills/*/SKILL.md` returns one hit
   and it is prose in `slashcommandcreator`, not frontmatter on any converted
   skill. A command fires only when typed; a skill can also be model-invoked.
   This is a decision, not a defect, so it went to the maintainer with the four
   options and their costs. **The maintainer chose on 2026-09-08 to leave all 21
   model-invocable and strike the parity claim in issue #5632.** Recorded as
   item 5 of the outcome section, including the cost: `ship` and `push-pr` push
   and open PRs, `pr-autofix` mutates PRs and can enable auto-merge, and the
   guards that keep those safe are the ones inside them rather than the
   invocation surface.

## Not accepted

The analyst's clearing condition included confirming the merging PR carries
`Fixes #5632`. PR #5640's body uses `Refs #5632`, which is correct while the
issue's remaining steps are not all closed by this PR alone, and universal.md
item 3 requires tying a closing keyword to a named hunk rather than adding one to
reach a green checklist. Left as `Refs`.

The security role's one hygiene note, a stale `# Referenced by .claude/commands/pr-review.md`
comment at the head of `pr-review-config.yaml`, is real and was fixed on contact.

## Standing risk

The high-level-advisor's: this branch is large and `main` moves several times a
day. `implemented: true` is true of this branch. Re-confirm it against the merge
result, not the branch tip, before trusting it.
