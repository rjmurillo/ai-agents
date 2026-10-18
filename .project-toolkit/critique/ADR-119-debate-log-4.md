# ADR Debate Log: ADR-119 Decisions 12 and 13, Shipped Plus Repo-Only Rules and Instructions

## Summary

- **Rounds**: 2 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-119-debate-log-3.md` (closed by consensus)
- **Outcome**: Consensus (4 Accept, 2 Disagree-and-Commit)
- **Final Status**: proposed
- **Records covered**: ADR-119 decisions 12 and 13, with their Alternatives, Consequences, Impact, and Reversibility edits; REQ-003 dated notes on REQ-003-006 and REQ-003-010.
- **Panel**: full six seats (architect, critic, independent-thinker, security, analyst, high-level-advisor), because the delta changes generator output, binplace rows, and the build's owned paths.
- **Owner directives, 2026-10-17**: "We may have additional instructions for THIS REPO ONLY in addition to the set that we ship ... Don't drop, merge at .github/" and, on rules, why they should not split like `ai-agents-*` skills. The panel reviewed consequences and implementation, not the directives.

## Round 1 Summary

### Key Issues Addressed

- architect, critic, independent-thinker, analyst (P1): decision 12 claimed an internal glob matches nothing in a consumer repository. False: consumers have `.claude/`. The first design kept internal globs in the shipped Copilot tree (`linkedOutputDirs`), which widened 11 shipped rules to consumers' own trees and reversed issue #4317 for Copilot. Fix: `linkedOutputDirs` removed. `src/copilot-cli/instructions` matches HEAD except one intended text line. `.github/instructions` links serve the filtered shipped copies. The in-repo cost (11 rules lose internal scopes for Copilot) is a Negative consequence. The scope-frontmatter stripper in `check_skill_md_portability.py` was reverted, since its premise was gone.
- critic, security (P1): a shipped rule that turned repo-only deadlocked the build on its own stale link. Fix: `rule_distribution.is_former_shipped_link` tolerates only the exact `../../src/claude/rules/<name>.md` link, and the atomic publish replaces it. Tests cover both flip directions, validate mode, and a refused foreign symlink. Disabling the tolerance fails two tests.
- security (P1): REQ-003 was not amended. Fix: dated notes after REQ-003-006 and REQ-003-010.
- analyst (P1): `rule_distribution.py` had no unit tests. Fix: `tests/build_scripts/test_rule_distribution.py`, 15 tests.
- architect, independent-thinker, high-level-advisor (P1): repo-only status is inferred from scope, not declared like skills. Deferred with justification: the scope already decides the Copilot skip (issue #4317), so a marker adds a second classifier that can disagree. A test pins the six names and checks agreement with the Copilot tree, so a flip needs a reviewed edit. The ADR records the alternative.
- P2 items fixed: `render_target` raises on a read error; a NO-REGEN shipped copy keeps its name in the shipped set; the eval resolver checks the named parent; stale "copies" wording in `copilot-cli.yaml` and `build_all.py`; compile-before-generate order stated; repo-local skill comparison replaces the agent one; linked instructions marked unverified on the cloud agent and VS Code; counts anchored to `60a2d6f06` (2026-10-17); Reversibility deletes the six real files; entry point stated.
- P2 items declined: ownership of `.github/instructions` real files stays a disk scan, because `generate_rules.py` prunes any real file there it did not render. Merging the config keys into one mode is deferred; two keys remain. The `_link_one` byte compare predates this delta.

### Agent Positions

| Agent | Round 1 | Round 2 |
|-------|---------|---------|
| architect | D&C | Accept |
| critic | D&C | D&C |
| independent-thinker | D&C | Accept |
| security | D&C | Accept |
| analyst | D&C | Accept |
| high-level-advisor | D&C | D&C |

## Round 2 Summary

### Key Issues Addressed

- critic (P1): `templates/rules/canonical-source-mirror.md` still said `.github/instructions` keeps the full internal path set. Fixed in the template; the rule shrank by 277 bytes.
- high-level-advisor (P1, owner decision): the chosen design keeps a cost once listed against a rejected alternative. The owner chose "Filtered links" on 2026-10-17 (D4). The ADR records it.
- independent-thinker, high-level-advisor (P2): one `build_all.py --check` run exited 2 with no diagnostic while a parallel build ran in another worktree. Not reproduced; reruns exited 0. Out of scope.

### Dissent

- critic (D&C): accepted after the canonical-source-mirror fix; flagged a stale Serena memory (`.serena/memories/pr-review/dispatched-model-reviewer-reliability.md:34`) for the owner.
- high-level-advisor (D&C): resolved by the owner's D4 answer.

### Next Steps

None blocking. After merge, confirm that linked `.github/instructions` load on the github.com cloud agent. Status stays `proposed` until the owner accepts.
