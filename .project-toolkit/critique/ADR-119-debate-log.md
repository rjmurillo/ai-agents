# ADR Debate Log: ADR-119 Symlink the Agent and Skill Dogfood Trees to the Plugin Tree

## Summary

- **Rounds**: 2 of 10
- **Prior debate log**: none
- **Outcome**: Consensus
- **Final Status**: proposed
- **Records covered**: ADR-119 (new), ADR-109 (dated amendment note: Alternative D adopted for agents and skills, 2026-09-15 support-file amendment retired for shipped skills), ADR-108 (dated amendment note: shipped-skill existence check moves to `src/claude/skills/<name>/`).
- **Panel**: full six seats (architect, critic, independent-thinker, security, analyst, high-level-advisor), because the change touches executable enforcement: binplace, the completion gate's CWE-59 check, and repository validators.
- **Owner decision taken before review**: on 2026-10-17 the owner chose the completion-gate design (follow a link only when the trusted remote-tracking ref holds the identical mode `120000` entry). The panel reviewed its correctness, not the choice.

## Round 1 Summary

### Key Issues Addressed

- architect (Block, P0): ADR-119 reversed ADR-109 Alternative D without naming it, and ADR-109 and ADR-108 still stated the opposite. Fix: Alternatives answers D's two rejection reasons; ADR-109 and ADR-108 carry dated notes pointing to ADR-119.
- architect, independent-thinker, critic (Block, P0): the stated rollback did nothing for skills. With `link: true` removed, the copy path wrote through each directory link, found equal bytes, and left every link. Fix: `binplace_manifest._replace_install_links` unlinks a leftover top-level install link on a copy row (drift under `--check`); `test_dropping_link_true_restores_real_directories` pins it.
- critic (Block, P0): `coverage.py` records the real path, so no shipped skill script was measured and the REQ-009 100% gate failed. Fix: `src/claude` joins `[tool.coverage.run] source`; `pytest.yml` `--include` names the `src/claude` path. Measured: 129 statements, 100%.
- critic (Block, P0): gates that `rglob` `.claude/skills` silently scanned only the 17 repo-local skills. Fix: a sweep pointed 12 more enumerators at `src/claude/skills`, re-keyed the vendor-portability baseline (17 entries, count unchanged), and added `tests/validation/test_symlinked_skill_scan_coverage.py` (17 tests asserting a nonzero examined count).
- security (P1): binplace linked a plugin entry that was itself a symlink, so a chain could leave the repository. Fix: `binplace_links.link_row` refuses such an entry, exit 2, with a test.
- security (P1): the pinned-link table was keyed relative to `_PROJECT_ROOT` while lookups used the git toplevel, so a subdirectory project root could borrow a deeper pin. Fix: `ls-tree --full-tree`, lookups keyed to the toplevel the table came from; four new negative tests (escaping text, absolute text, cycle, subdirectory root). A mutation dropping `--full-tree` fails one test.
- critic (P1): Windows jobs beyond cli-smoke; link creation without privilege raised a traceback. Fix: `core.symlinks` in the `pytest.yml` Windows job; `OSError` becomes exit 2 naming Developer Mode and `core.symlinks`.
- independent-thinker, high-level-advisor, critic (P1): missing consequences: git refuses paths beyond a symlink, the gate transition window until links reach `origin/main`, the plugin-dogfood alternative. Fix: all three added to the ADR.
- architect (P1): MADR gaps. Fix: Decision Drivers, Rationale, Positive/Negative/Neutral consequences, Related Decisions; decisions 8 and 9 marked as forced sub-decisions with drivers.
- analyst, high-level-advisor (P1): 649 counted only skill files. Fix: 679 (649 skill files plus 30 agent files), anchored to commit `28eb90c9e` (2026-10-17).

### Major Changes Made

- ADR-119 rewritten to the repository template.
- Code: rollback path, symlinked-entry refusal, symlink `OSError` handling, gate toplevel keying, coverage config, Windows CI step, 12 enumerators, prompts row source.

### Agent Positions

| Agent | Round 1 | Round 2 |
|-------|---------|---------|
| architect | Block | Accept |
| critic | Block | Accept |
| independent-thinker | Block | Accept |
| security | Disagree-and-Commit | Accept |
| analyst | Accept | Accept |
| high-level-advisor | Accept | Accept |

## Round 2 Summary

### Key Issues Addressed

Every seat verified its round-1 findings against files and commands and marked all P0 and P1 items resolved. Remaining P2 items and their disposition:

- critic: stale docstring naming `./.claude` as the Claude marketplace root. Fixed (`./src/claude`).
- critic: `build-bundle.ts` followed links with no containment. Fixed: a followed link must resolve inside the repository or the build fails; checked with an outside link (refused) and the real tree (642 files).
- security: the install sweep skipped any name ending in `.binplace-link` or `.binplace-old`. Fixed: only this module's own transient names for an owned entry are skipped; `test_a_suffix_shaped_stray_is_still_reported` pins it.
- architect: Copilot CLI loading of linked skills unprobed. Recorded in Prior Art as unverified and accepted.
- independent-thinker: why per-file agent links. Recorded in Alternatives.
- analyst: 135 index links and the 121 `.claude/skills/` entries. Recorded in Consequences.
- critic: completion-gate resolvers that do not return the post-link path. Recorded as known gate debt (fails closed).
- independent-thinker: one `cat-file` per link when loading the pin table. Deferred: correctness is unaffected; about 135 calls, only when the gate meets a link.
- high-level-advisor: no contributor-facing Windows note. Deferred to a follow-up; the exit-2 message names the fix at the point of failure.

### Major Changes Made

- P2 fixes above, applied after the round-2 verdicts. No P0 or P1 change followed the vote.

### Next Steps

None blocking. Status stays `proposed` until the owner accepts.
